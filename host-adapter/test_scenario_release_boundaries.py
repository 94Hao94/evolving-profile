"""Execution-facing identity/constraint/capacity boundaries, not topic rules."""
from copy import deepcopy
import pytest
from lib.scenario_hierarchical_review import build_review_request,expand_selected_aliases


def relation_request(text,version='source-selection.v3'):
    return build_review_request('merge',{'wire_contract':version},
        {'atoms':[{'atom_id':'first','authority':'user_claim','action':'First project'},
                  {'atom_id':'second','authority':'user_claim','action':'Second project'}],
         'source_pages':[{'page_id':'source','text':text,'role':'user','source_readback':True}]},
        {'partition_input_tokens':12000,'partition_output_tokens':2000})


def same_object(version='source-selection.v3'):
    return {'wire_schema':version,'relations':[{'kind':'same_object','from':'i0','to':'i1',
        'sources':['p0'],'state':'supported','reason':'model identity claim'}],
        'record_obligations':[],'states':[],'discovery_complete':True}


@pytest.mark.parametrize('text',[
    '甲校项目A预算100万元。甲校项目B预算200万元。两者是独立项目，不能合并预算。',
    'Alpha and Beta are independent projects for one client. Do not combine their budgets.',
    '同一客户的采购任务和研究任务，分别管理。',
    'The old and new identifiers may refer to one project, but this has not been established.',
])
def test_v3_quote_presence_cannot_promote_model_identity(text):
    req=relation_request(text);raw=same_object();original=deepcopy(raw)
    value=expand_selected_aliases(raw,req)
    assert value['object_links']==[]
    relation=value['obligations'][0]
    assert relation['state']=='open' and relation['identity_verification']=='model_hypothesis_only'
    assert relation['evidence_refs'][0]['quote']==text
    assert relation['model_reported_state']=='supported' and raw==original
    assert [r['atom_id'] for r in req['inputs']['atoms']]==['first','second']


def test_old_v2_identity_wire_is_not_silently_reinterpreted():
    value=expand_selected_aliases(same_object('source-selection.v2'),relation_request('original evidence','source-selection.v2'))
    assert len(value['object_links'])==1 and value['obligations'][0]['state']=='supported'


def test_v3_readback_label_cannot_launder_open_identity():
    req=relation_request('Projects A and B remain distinct.')
    req=build_review_request('readback',req['binding'],{**req['inputs'],'obligations':[
        {'obligation_id':'pending','atom_ids':['first','second'],'relation_kind':'same_object',
         'from_item':'first','to_item':'second','state':'open','reason':'identity unknown','evidence_refs':[]}]},req['limits'])
    raw=same_object();raw['relations']=[]
    raw['record_obligations']=[{'id':'o0','kind':'identity','items':['i0','i1'],'sources':['p0'],
        'state':'supported','reason':'model says yes'}]
    row=expand_selected_aliases(raw,req)['obligations'][0]
    assert row['state']=='open' and row['identity_verification']=='model_hypothesis_only'


def test_v3_positive_identity_does_not_make_global_coverage_green(tmp_path):
    from test_scenario_hierarchical_end_to_end import setup,controlled
    from test_scenario_review_partial import run
    from lib.scenario_hierarchical_store import HierarchicalStore
    state,_,s,parts,settings,b=setup(tmp_path);base=controlled([])
    def provider(req):
        value=base(req)
        if req['stage']=='merge':
            value['result']['relations']=[{'kind':'same_object','from':'i0','to':'a0','sources':['p0'],
                'state':'supported','reason':'same client is not proof'}]
        if req['stage']=='readback':
            o=req['model_request']['inputs']['record_obligations'][0]
            value['result']['record_obligations']=[{'id':o['id'],'kind':o['kind'],'items':o['items'],
                'state':'supported','reason':'model positive again','sources':['p0']}]
        return value
    result=run(state,s,parts,settings,b,provider)
    graph=HierarchicalStore(state/'hierarchical/graphs.sqlite3',readonly=True).load_current(s['scope'],s['permission'])['graph']
    assert result['coverage']['target_complete'] is False and result['coverage']['scope_review']=='unresolved'
    assert graph['object_links']==[] and graph['obligations'][0]['state']=='open'
    assert graph['obligations'][0]['identity_verification']=='model_hypothesis_only'
    assert result['atom_count']==1 and result['assistant_claim_count']==1


@pytest.mark.parametrize('original',[
    '找出我最近两三天说过的：AI最重要的是提问能力。请给原话。',
    'Only use the source document. Every slide, not some slides; do not publish yet.',
    '这次可以用，下一次未必适用；仅当前项目，不是全部项目。',
])
def test_lossy_summary_cannot_claim_constraint_fidelity_and_raw_route_preserves_text(tmp_path,original):
    from test_scenario_source_codec import source
    from test_scenario_coverage_incremental import job
    from lib.scenario_coverage_incremental import process_coverage_job
    from lib.scenario_coverage_store import CoverageStore
    from lib.scenario_coverage_partition import partition_snapshot
    from lib.scenario_coverage_contract import validate_settings
    from test_scenario_hierarchical_review import budget
    from test_scenario_hierarchical_end_to_end import controlled
    from test_scenario_review_partial import run
    from lib.scenario_hierarchical_read import read_hierarchical_view
    from lib.scenario_hierarchical_store import HierarchicalStore
    root,_,_=source(tmp_path,text=original);state=tmp_path/'state'
    result=process_coverage_job(job(),root,{},store_root=state)
    s=CoverageStore(state/'coverage.sqlite3').read(result['snapshot_id'])
    settings=validate_settings({'mode':'assisted','model_trial':True,'review_protocol':'hierarchical_review.v1'})
    result=run(state,s,partition_snapshot(s,capacity=1000),settings,budget(tmp_path),controlled([]))
    graph=HierarchicalStore(state/'hierarchical/graphs.sqlite3',readonly=True).load_current(s['scope'],s['permission'])['graph']
    # Fixture deliberately says only "inspect"; a positive leaf review must
    # not turn this demonstrably lossy summary into lossless constraints.
    assert graph['atoms'][0]['action']=='inspect'
    assert graph['atoms'][0]['constraint_use']=='original_source_required'
    assert result['coverage']['constraint_use']=='original_source_required'
    def read(view,**kw):return read_hierarchical_view(state,job()['session_id'],view,
        cursor=kw.pop('cursor',None),permission=s['permission'],expected_scope=s['scope'],requirement_id=kw.pop('requirement_id',None),**kw)
    req=read('requirements')['requirements'][0]
    assert req['constraint_use']=='original_source_required' and req['summary_fidelity']=='not_certified_lossless'
    assert req['source_locator']['coverage_view']=='source'
    raw=read('source',requirement_id=req['requirement_id'])
    assert raw['raw_source']['text']==original and raw['source_readback'] is True
    assert raw['record_source_complete_in_response'] is True
    assert raw['constraint_use']=='original_source_page_not_verified_outcome'


def test_partial_original_read_cannot_claim_complete_constraint_coverage(tmp_path):
    from test_scenario_source_codec import source
    from test_scenario_coverage_incremental import job
    from lib.scenario_coverage_incremental import process_coverage_job
    from lib.scenario_coverage_store import CoverageStore
    from lib.scenario_hierarchical_read import read_hierarchical_view
    original='仅限当前项目。🙂'*700
    root,_,_=source(tmp_path,text=original);state=tmp_path/'state'
    result=process_coverage_job(job(),root,{},store_root=state)
    s=CoverageStore(state/'coverage.sqlite3').read(result['snapshot_id'])
    def read(view,**kw):return read_hierarchical_view(state,job()['session_id'],view,
        cursor=kw.pop('cursor',None),permission=s['permission'],expected_scope=s['scope'],requirement_id=kw.pop('requirement_id',None),**kw)
    requirement=read('requirements')['requirements'][0]['requirement_id']
    first=read('source',requirement_id=requirement)
    assert first['coverage_cursor'] and first['record_source_complete_in_response'] is False
    chunks=[first['raw_source']['text']];cursor=first['coverage_cursor']
    while cursor:
        page=read('source',requirement_id=requirement,cursor=cursor)
        assert page['record_source_complete_in_response'] is False  # final page isn't the entire response scope
        chunks.append(page['raw_source']['text']);cursor=page['coverage_cursor']
    assert ''.join(chunks)==original


def test_v3_actual_provider_envelope_fits_original_long_record_without_truncation():
    from lib.scenario_coverage_provider import ConfiguredCoverageProvider
    from lib.scenario_coverage_contract import canonical
    # No provider configuration/key needed: only the production serializer.
    provider=ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_BASE_URL':'https://example.invalid/v1',
        'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_API_KEY':'not-a-key'})
    text='能力询问、条件、否定与未知。'*64
    inputs={'atoms':[],'assistant_claims':[{'atom_id':'long-report','authority':'assistant_report','claim':text,
        'action':'分析前提、可行路线和未知条件。'*30,'source_order':[7]}],
        'source_pages':[{'page_id':'raw','text':text,'role':'assistant','sequence':7,'source_readback':True}],
        'boundaries':[{'node_id':'node','children':['left','right']}],
        'prior_states':[{'atom_id':'old','state':'unresolved','evidence_refs':[]}]}
    req=build_review_request('merge',{'wire_contract':'source-selection.v3'},inputs,
        {'partition_input_tokens':12000,'partition_output_tokens':2000})
    assert len(canonical(provider.request_envelope(req)))<=12000
    assert req['inputs']==inputs and req['model_request']['inputs']['source_pages'][0]['text']==text
    assert req['model_request']['inputs']['assistant_claims'][0]['reported_statement_pages']==['p0']


def test_oversized_merge_retains_source_route_and_reports_bounded_continuation(tmp_path):
    from test_scenario_hierarchical_end_to_end import setup,controlled
    from test_scenario_review_partial import run
    from lib.scenario_hierarchical_read import read_hierarchical_view
    from test_scenario_coverage_incremental import job
    state,_,s,parts,settings,b=setup(tmp_path);calls=[];base=controlled(calls)
    class Provider:
        def __call__(self,req):return base(req)
        def request_envelope(self,req):
            return {'request':req['model_request'],'fixed_header':'x'*30000} if req['stage']=='merge' else req['model_request']
    result=run(state,s,parts,settings,b,Provider())
    assert result['status']=='capacity_paused' and result['coverage']['target_complete'] is False
    diagnostic=result['capacity_recovery']
    assert diagnostic['stage']=='merge' and diagnostic['wire_bytes']>diagnostic['input_bound']
    assert diagnostic['source_scope_reduced'] is False and diagnostic['unprocessed_record_ids']
    assert diagnostic['next_action']=='read_original_or_resume_with_adequate_capacity'
    assert [c['stage'] for c in calls]==['extract','leaf']
    view=read_hierarchical_view(state,job()['session_id'],'requirements',cursor=None,
        permission=s['permission'],expected_scope=s['scope'],requirement_id=None)
    assert view['capacity_recovery']==diagnostic
    page=read_hierarchical_view(state,job()['session_id'],'source',cursor=None,permission=s['permission'],
        expected_scope=s['scope'],requirement_id=view['requirements'][0]['requirement_id'])
    assert page['raw_source']['text']=='仅检查草稿。'


def test_failed_merge_preflight_reports_every_unexecuted_record_not_only_large_one():
    from lib.scenario_evidence_capsule import build_capsules
    from lib.scenario_hierarchical_transport import merge_pages
    from lib.scenario_hierarchical_review import InputCapacityExceeded
    records=[{'atom_id':name,'authority':'user_requirement','action':action,'source_quote':'source'}
        for name,action in [('small-before','inspect'),('oversized','x'*10000),('small-after','read')]]
    limits={'partition_input_tokens':5000,'partition_output_tokens':2000}
    capsule=build_capsules({},records,[],[],limits)
    with pytest.raises(InputCapacityExceeded) as caught:
        merge_pages({'wire_contract':'source-selection.v3'},{'node_id':'n'},
            ['small-before','oversized','small-after'],capsule,[],limits,lambda _:None)
    assert caught.value.unprocessed_record_ids==['small-before','oversized','small-after']
