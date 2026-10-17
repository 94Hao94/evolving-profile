import copy
import json
import subprocess
import sys
from pathlib import Path
import pytest
from test_scenario_hierarchical_end_to_end import setup,controlled,model_source_text
from test_scenario_coverage_incremental import job
from lib.scenario_coverage_contract import fingerprint
from lib.scenario_coverage_incremental import process_coverage_job
from lib.scenario_coverage_partition import partition_snapshot
from lib.scenario_coverage_read import read_coverage_view
from lib.scenario_coverage_store import CoverageStore
from lib.scenario_coverage_budget import CoverageBudget
from lib.scenario_hierarchical_incremental import process_hierarchical_stages,authorize_evaluation
from lib.scenario_hierarchical_store import HierarchicalStore
from lib.scenario_hierarchical_review import restore_review,logical_inputs


def run(state,s,parts,settings,budget,provider):
    return process_hierarchical_stages(job(),s,parts,settings,root=state,provider=provider,budget=budget,
        permission_getter=lambda:s['permission'],scope_getter=lambda:s['scope'],authorize_request=lambda:None,parent_lease_valid=None,
        evaluation_authorization=authorize_evaluation(s,budget,'review-regression'))


def graph(state,s):return HierarchicalStore(state/'hierarchical/graphs.sqlite3').load_current(s['scope'],s['permission'])['graph']


def append_and_reload(state,s,texts):
    with open(s['location']['path'],'a') as f:
        for text in texts:f.write(json.dumps({'type':'response_item','payload':{'type':'message','role':'user',
            'content':[{'type':'input_text','text':text}]}})+'\n')
    process_coverage_job(job(),s['location']['root'],{},store_root=state)
    status=json.loads((state/'status'/f"{job()['session_id']}.json").read_text())
    return CoverageStore(state/'coverage.sqlite3').read(status['snapshot_id'])


def read(state,s,view,**kw):return read_coverage_view(state,job()['session_id'],view,permission=s['permission'],review_protocol='hierarchical_review.v1',**kw)


def test_restored_receipt_never_attests_serialized_rebind(tmp_path):
    state,_,s,parts,settings,budget=setup(tmp_path)
    run(state,s,parts,settings,budget,controlled([]))
    saved=graph(state,s)['leaf_receipts'][0]
    evil=copy.deepcopy(saved);inputs=copy.deepcopy(saved['request']['inputs'])
    inputs['proposal']['atoms'][0]['action']='PUBLISH WITHOUT APPROVAL'
    evil['rebind']={'binding':saved['request']['binding'],'inputs':inputs}
    restored=restore_review(evil,saved['request'],budget)
    assert restored is None or logical_inputs(restored)['proposal']['atoms'][0]['action']!='PUBLISH WITHOUT APPROVAL'


def test_valid_residual_without_kind_remains_readable(tmp_path):
    state,_,s,parts,settings,budget=setup(tmp_path);base=controlled([])
    def provider(r):
        out=base(r)
        if r['stage']=='extract':
            a=out['result']['proposal']['items'][0]
            reports=[r for r in out['result']['proposal']['items'] if r['kind']=='report']
            out['result']['proposal']={'items':[{'source_cards':a['source_cards'],'kind':'non_substantive'},*reports]}
        return out
    assert run(state,s,parts,settings,budget,provider)['status']=='scope_reviewed'
    assert read(state,s,'requirements')['requirements'][0]['text']=='仅检查草稿。'


def test_assistant_claim_and_state_proposals_reach_parent_and_navigation(tmp_path):
    state,_,s,parts,settings,budget=setup(tmp_path);base=controlled([]);seen=[]
    def provider(r):
        out=base(r);i=r['model_request']['inputs']
        if r['stage']=='extract':
            a=next(v for v in i['partition']['primary'] if v['role']=='assistant')
            out['result']['proposal']['items']=[r for r in out['result']['proposal']['items'] if r['kind']!='report']
            out['result']['proposal']['items'].append({'kind':'report','claim':'助手声称已完成',
                'source_cards':[a['span_id']]})
        if r['stage']=='merge':
            seen.extend(i.get('assistant_claims',[]))
            out['result']['states']=[{'item':i['atoms'][0]['atom_id'],'state':'current','sources':[]}]
        return out
    result=run(state,s,parts,settings,budget,provider)
    assert seen and graph(state,s)['assistant_claims']
    assert graph(state,s)['states'][0]['state']=='current'
    assert graph(state,s)['states'][0]['verification']=='model_proposal_only'
    assert result['external_fact_verified'] is False


def test_partial_failure_preserves_entire_raw_target_inventory(tmp_path):
    state,_,s,_,settings,budget=setup(tmp_path)
    s=append_and_reload(state,s,['第二项要求。','第三项要求。']);parts=partition_snapshot(s,capacity=40)
    base=controlled([]);n=0
    def provider(r):
        nonlocal n
        if r['stage']=='extract':
            n+=1
            if n==2:raise TimeoutError()
        return base(r)
    result=run(state,s,parts,settings,budget,provider)
    requirements=read(state,s,'requirements')
    assert result['status']!='scope_reviewed'
    assert len(requirements['requirements'])==3
    assert '第二项要求。' in [r['text'] for r in requirements['requirements']]
    assert requirements['status']!='local_candidate'
    assert graph(state,s)['coverage']['groups']


def test_normalized_locator_coordinates_match_original_or_explicit_unknown(tmp_path):
    from test_scenario_coverage_partition import snapshot
    from lib.scenario_intent_atoms import validate_atom_proposal
    text='<external_codex_apps_open_page>{"page_id":"p1"}</external_codex_apps_open_page>不要发布。'
    s=snapshot(tmp_path,text);p=partition_snapshot(s,capacity=1000)['partitions'][0];span=p['primary'][0]
    row={'source_refs':[{'span_id':span['span_id'],'start':0,'end':5,'quote':'不要发布。'}],
        'kind':'constraint','authority':'user_requirement','action':'发布','conditions':[],'negation':True,'exceptions':[],
        'object_hypotheses':[],'time':{},'local_state':'expressed'}
    checked=validate_atom_proposal(s,p,{'atoms':[row],'residuals':[],'assistant_claims':[]})
    assert checked['errors']==[]
    ref=checked['atoms'][0]['source_refs'][0]
    assert text[ref['message_start']:ref['message_end']]==ref['quote']
    assert ref['normalized_start']==0


def test_model_change_readiness_block_stales_old_graph_without_spending(tmp_path):
    state,_,s,parts,settings,budget=setup(tmp_path)
    class Provider:
        def __init__(self,name):self.review_identity={'model':name};self.base=controlled([])
        def __call__(self,r):return self.base(r)
    run(state,s,parts,settings,budget,Provider('A'))
    before=budget.status()['requests_used']
    result=process_hierarchical_stages(job(),s,parts,settings,root=state,provider=Provider('B'),budget=budget,
        permission_getter=lambda:s['permission'],scope_getter=lambda:s['scope'],authorize_request=None,parent_lease_valid=None)
    assert result['reason']=='semantic_readiness_unverified'
    overview=read(state,s,'overview')
    assert overview['status']=='stale' and overview['coverage']['target_complete'] is False
    assert overview['coverage']['intent_review']!='complete'
    assert all(g['status']!='scope_reviewed' for g in overview['coverage']['groups'].values())
    assert budget.status()['requests_used']==before


def test_malformed_obligation_identifier_is_structured_rejection(tmp_path):
    state,_,s,parts,settings,budget=setup(tmp_path);base=controlled([])
    def provider(r):
        out=base(r)
        if r['stage']=='merge':out['result']['record_obligations']=[{'id':['bad'],'kind':'reference','items':[r['model_request']['inputs']['atoms'][0]['atom_id']],
            'state':'open','reason':'x','sources':[]}]
        return out
    result=run(state,s,parts,settings,budget,provider)
    assert result['status']!='scope_reviewed' and result['budget']['requests_used']==3


def test_acceptance_cli_without_semantic_cases_returns_nonready_not_traceback(tmp_path):
    root=Path(__file__).resolve().parents[1]
    p=subprocess.run([sys.executable,str(root/'scripts/verify-ep-acceptance.py'),
        '--evidence-root',str(tmp_path/'evidence')],capture_output=True,text=True)
    assert p.returncode==2 and 'Traceback' not in p.stderr
    assert json.loads(p.stdout)['hierarchical_semantic_ready'] is False


def test_transport_fallback_is_reserved_not_nested_or_semantic_veto_retry(tmp_path):
    state,_,s,parts,settings,budget=setup(tmp_path);base=controlled([])
    class Primary:
        review_identity={'model':'primary'}
        def fallback_providers(self):return [base]
        def __call__(self,r):raise TimeoutError()
    result=run(state,s,parts,settings,budget,Primary())
    assert result['status']=='scope_reviewed'
    assert budget.status()['requests_used']==6 and budget.status()['unknown_usage_requests']==3


def test_explicit_resume_can_pay_for_retry_without_resetting_original_charge(tmp_path):
    state,_,s,parts,settings,budget=setup(tmp_path);base=controlled([]);fail=True
    def provider(r):
        nonlocal fail
        if fail:fail=False;raise TimeoutError()
        return base(r)
    first=run(state,s,parts,settings,budget,provider)
    assert first['status']!='scope_reviewed'
    result=run(state,s,parts,settings,budget,provider)
    assert result['status']=='scope_reviewed' and budget.status()['requests_used']==4
    assert budget.status()['unknown_usage_requests']==1


def test_completed_capacity_fallback_cache_is_reused_without_retrying_failed_primary(tmp_path):
    state,_,s,parts,settings,budget=setup(tmp_path);base=controlled([])
    class Primary:
        review_identity={'model':'small-output-profile'}
        def fallback_providers(self):return [base]
        def __call__(self,r):raise ValueError('coverage_response_incomplete')
    first=run(state,s,parts,settings,budget,Primary());used=budget.status()['requests_used']
    assert first['status']=='scope_reviewed'
    second=run(state,s,parts,settings,budget,Primary())
    assert second['status']=='scope_reviewed' and second['model_calls']==0
    assert budget.status()['requests_used']==used


def test_real_partition_boundary_can_form_one_conditional_intent(tmp_path):
    state,_,s,_,settings,budget=setup(tmp_path)
    # Replace the entire fixture with a short condition split by transport.
    from test_scenario_source_codec import source
    root=tmp_path/'boundary';root.mkdir();sessions,_,_=source(root,text='仅草稿时不要发布')
    state=root/'state';r=process_coverage_job(job(),sessions,{},store_root=state)
    s=CoverageStore(state/'coverage.sqlite3').read(r['snapshot_id']);parts=partition_snapshot(s,capacity=12)
    base=controlled([])
    def provider(r):
        out=base(r)
        if r['stage']=='extract':
            spans=[a for a in r['model_request']['inputs']['partition']['primary'] if a['role']=='user']
            reports=[row for row in out['result']['proposal']['items'] if row['kind']=='report']
            if spans:out['result']['proposal']['items']=[{'source_cards':[a['span_id'] for a in spans],
                'kind':'constraint','action':'发布','conditions':['仅草稿时'],
                'negation':True,'exceptions':[],'object_hypotheses':[],'time':{},'local_state':'expressed'},*reports]
        return out
    result=run(state,s,parts,settings,budget,provider)
    assert result['status']=='scope_reviewed'
    assert graph(state,s)['atoms'][0]['source_quote']=='仅草稿时不要发布'


def test_many_small_leaves_use_bounded_capsule_pages_to_complete(tmp_path):
    state,_,s,_,settings,_=setup(tmp_path)
    s=append_and_reload(state,s,[f'request {i}: preserve files and inspect.' for i in range(11)])
    parts=partition_snapshot(s,capacity=40);settings['limits']['partition_input_tokens']=6000
    budget=CoverageBudget(state/'ample-fixture.sqlite3',job_id='fixture',budget_identity='isolated',parent_attempts=0,max_requests=200,max_tokens=3000000)
    result=run(state,s,parts,settings,budget,controlled([]))
    assert result['status']=='scope_reviewed'
    saved=graph(state,s)
    assert saved['capsules']['owners'] and saved['coverage']['target_complete'] is True


def test_live_saved_provider_change_stales_read_even_without_another_job(tmp_path):
    state,_,s,parts,settings,budget=setup(tmp_path)
    run(state,s,parts,settings,budget,controlled([]))
    # Model metadata is a host read input, not a model-result field.
    from lib.scenario_coverage_read import read_coverage_view
    result=read_coverage_view(state,job()['session_id'],'overview',permission=s['permission'],
        review_protocol='hierarchical_review.v1',expected_review_binding={'provider':{'model':'different'}})
    assert result['status']=='stale' and result['coverage']['target_complete'] is False


def test_full_relation_reason_and_all_endpoints_are_page_readable(tmp_path):
    state,_,s,parts,settings,budget=setup(tmp_path);base=controlled([])
    reason='完整的关系解释'*200
    def provider(r):
        out=base(r)
        if r['stage']=='merge':out['result']['record_obligations']=[{'id':'new:check','kind':'reference','items':[r['model_request']['inputs']['atoms'][0]['atom_id']],
            'state':'open','reason':reason,'sources':[]}]
        if r['stage']=='readback':out['result']['record_obligations']=[]
        return out
    run(state,s,parts,settings,budget,provider)
    text=[];cursor=None
    while True:
        page=read(state,s,'relations',cursor=cursor)
        text.extend(r['evidence_quote'] for r in page['relations'])
        assert page['relations'][0]['atom_ids']
        cursor=page['coverage_cursor']
        if not cursor:break
    assert ''.join(text)==reason
