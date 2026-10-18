import json
try:
    from lib.scenario_hierarchical_incremental import process_hierarchical_stages,authorize_evaluation
except ImportError:process_hierarchical_stages=None
from lib.scenario_coverage_contract import validate_settings
from lib.scenario_coverage_incremental import process_coverage_job
from lib.scenario_coverage_partition import partition_snapshot
from lib.scenario_coverage_store import CoverageStore
from lib.scenario_coverage_budget import CoverageBudget
from test_scenario_coverage_incremental import job
from test_scenario_source_codec import source


def model_source_text(inputs,span):
    return next(c['text'] for c in inputs['source_cards'] if c['card_id']==span['span_id']) if 'source_cards' in inputs else span['text']


def corrupt_source(row):
    if 'source_cards' in row:row['source_cards']=['unknown-source-card']
    else:row['source_refs'][0]['quote']='invented'


def controlled(calls):
    def provider(request):
        calls.append(request);p=request['model_request'];inputs=p['inputs']
        result={'accept':True,'accepted_scope':'source_attribution_and_intent_only','issues':[],'read_ids':[r['id'] for r in p['catalog']],
            'assistant_reports_are_unverified':True}
        version=p.get('wire_contract')
        if version:
            from test_scenario_review_axes import typed
            result=typed(request)['result'] if p['stage']!='extract' else {'context_requests':[]}
            result['wire_schema']=version
        if p['stage']=='extract':
            items=[];cards={c['card_id']:c['text'] for c in inputs.get('source_cards',[])}
            for s in inputs['partition']['primary']:
                text=cards[s['span_id']] if version else s['text']
                if s['role']=='user' and text:
                    refs={'source_cards':[s['span_id']]} if version else {'source_refs':[{'span_id':s['span_id'],'start':0,'end':len(text),'quote':text}]}
                    items.append({**refs,
                        'kind':'constraint','authority':'user_requirement','action':'inspect','conditions':[],
                        'negation':False,'exceptions':[],'object_hypotheses':[],
                        'time':{'event':None,'effective':None},'local_state':'expressed'})
            if version=='source-selection.v3':
                result['proposal']={'items':[{k:v for k,v in row.items() if k!='authority'} for row in items]}
                result['proposal']['items'].extend({'source_cards':[s['span_id']],'kind':'report','action':'助手原文记录'}
                    for s in inputs['partition']['primary'] if s['role']=='assistant' and cards[s['span_id']])
            else:result['proposal']={'atoms':items,'residuals':[],'assistant_claims':[]}
        elif p['stage']=='leaf':
            if not version:result.update(intent_sufficient=True,conditions_preserved=True)
        elif version:result.update(discovery_complete=True,relations=[],record_obligations=[],states=[])
        else:result.update(discovery_complete=True,obligations=[],object_links=[])
        return {'result':result,'usage':{'total_tokens':80},'transport':'isolated_fixture_not_live_provider'}
    return provider


def setup(tmp_path):
    assert process_hierarchical_stages is not None
    root,_,_=source(tmp_path,text='仅检查草稿。');state=tmp_path/'state'
    result=process_coverage_job(job(),root,{},store_root=state)
    store=CoverageStore(state/'coverage.sqlite3');s=store.read(result['snapshot_id'])
    parts=partition_snapshot(s,capacity=1000)
    settings=validate_settings({'mode':'assisted','model_trial':True,'review_protocol':'hierarchical_review.v1'})
    settings['limits']['partition_input_tokens']=20000
    budget=CoverageBudget(state/'requests.sqlite3',job_id=job()['session_id'],budget_identity=s['semantic_budget_identity'],
        parent_attempts=1,max_requests=20,max_tokens=100000)
    return state,store,s,parts,settings,budget


def test_shadow_never_dispatches(tmp_path):
    state,store,s,parts,settings,budget=setup(tmp_path)
    settings['mode']='source_shadow';calls=[]
    result=process_hierarchical_stages(job(),s,parts,settings,root=state,provider=controlled(calls),budget=budget,
        permission_getter=lambda:job()['permission'],scope_getter=lambda:s['scope'],authorize_request=None,parent_lease_valid=None)
    assert result['model_calls']==0 and calls==[]
    assert result['published'] is False


def test_dropped_source_partition_cannot_become_declared_scope_complete(tmp_path):
    from lib.scenario_coverage_partition import partition_snapshot
    state,store,s,_,settings,budget=setup(tmp_path);parts=partition_snapshot(s,capacity=40)
    parts['partitions'].pop();calls=[]
    result=process_hierarchical_stages(job(),s,parts,settings,root=state,provider=controlled(calls),budget=budget,
        permission_getter=lambda:s['permission'],scope_getter=lambda:s['scope'],authorize_request=None,parent_lease_valid=None,
        evaluation_authorization=authorize_evaluation(s,budget,'fixture'))
    assert result['status']=='unavailable' and calls==[]


def test_new_assisted_without_readiness_never_spends(tmp_path):
    state,store,s,parts,settings,budget=setup(tmp_path);calls=[]
    r=process_hierarchical_stages(job(),s,parts,settings,root=state,provider=controlled(calls),budget=budget,
        permission_getter=lambda:job()['permission'],scope_getter=lambda:s['scope'],authorize_request=None,parent_lease_valid=None)
    assert r['reason']=='semantic_readiness_unverified' and calls==[]


def test_qualification_is_bound_to_protocol_model_and_independent_answer_evidence(tmp_path):
    from lib import scenario_hierarchical_incremental as mod
    assert hasattr(mod,'qualification_allows')
    assert mod.qualification_allows({'semantic_ready':True}, {'provider':{}},{}) is False
    assert mod.qualification_allows(None, {'provider':{}},{}) is False


def test_isolated_complete_fixture_keeps_legacy_files_and_resumes_cache(tmp_path):
    state,store,s,parts,settings,budget=setup(tmp_path);calls=[]
    legacy=state/'navigation';legacy.mkdir();(legacy/'old.json').write_text('{"accepted":true}')
    grant=authorize_evaluation(s,budget,'frozen-fixture-plan')
    def run():return process_hierarchical_stages(job(),s,parts,settings,root=state,provider=controlled(calls),budget=budget,
        permission_getter=lambda:job()['permission'],scope_getter=lambda:s['scope'],authorize_request=None,
        parent_lease_valid=None,evaluation_authorization=grant)
    first=run()
    assert first['status']=='scope_reviewed' and first['coverage']['target_complete'] is True
    assert first['legacy_v3_acceptance'] is False and first['external_fact_verified'] is False
    assert len(calls)==3 and budget.status()['requests_used']==3
    assert (legacy/'old.json').read_text()=='{"accepted":true}'
    second=run()
    assert second['model_calls']==0 and len(calls)==3


def test_open_obligation_reads_real_source_before_can_close(tmp_path):
    state,store,s,parts,settings,budget=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(request):
        r=base(request);p=request['model_request'];i=p['inputs']
        if p['stage']=='merge':
            r['result']['record_obligations']=[{'id':'new:check-condition','kind':'condition','items':[i['atoms'][0]['atom_id']],
                'state':'open','reason':'needs original condition','sources':[]}]
        elif p['stage']=='readback':
            o=i['record_obligations'][0];page=i['source_pages'][0]
            r['result']['record_obligations']=[{'id':o['id'],'kind':'condition','items':o['items'],
                'state':'supported','reason':'original condition read','sources':[page['page_id']]}]
        return r
    result=process_hierarchical_stages(job(),s,parts,settings,root=state,provider=provider,budget=budget,
        permission_getter=lambda:job()['permission'],scope_getter=lambda:s['scope'],authorize_request=None,
        parent_lease_valid=None,evaluation_authorization=authorize_evaluation(s,budget,'readback-fixture'))
    assert any(r['stage']=='readback' for r in calls)
    assert result['coverage']['target_complete'] is True
    assert result['raw_review_pages']>0 and result['source_readback'] is False
