import json
import pytest
from test_scenario_hierarchical_end_to_end import setup,controlled
from test_scenario_review_partial import run,axes_provider
from test_scenario_review_context import context_fixture,recover
from test_scenario_review_axes import typed
from test_scenario_hierarchical_review import request,budget
from test_scenario_source_codec import source
from test_scenario_coverage_incremental import job
from lib.scenario_hierarchical_review import build_review_request,execute_review
from lib.scenario_hierarchical_execution import ReviewExecutor
from lib.scenario_hierarchical_store import HierarchicalStore
from lib.scenario_coverage_incremental import process_coverage_job
from lib.scenario_coverage_store import CoverageStore
from lib.scenario_coverage_partition import partition_snapshot


@pytest.mark.parametrize('stage',['merge','readback'])
def test_discovery_scope_uncertainty_cannot_disappear_from_parent_axes(tmp_path,stage):
    state,store,s,parts,settings,b=setup(tmp_path);calls=[];base=axes_provider(calls,scope='resolved')
    def provider(req):
        v=base(req);i=req['model_request']['inputs']
        if req['stage']==stage:v['result']['review_axes']['scope'].update(status='unresolved',issues=['project identity unknown'])
        if stage=='readback' and req['stage']=='merge':
            v['result']['record_obligations']=[{'id':'new:check','kind':'reference','items':[i['atoms'][0]['atom_id']],'state':'open','reason':'check original','sources':[]}]
        if req['stage']=='readback':
            o=i['record_obligations'][0];p=i['source_pages'][0]
            v['result']['record_obligations']=[{'id':o['id'],'kind':'reference','items':o['items'],
                'state':'supported','reason':'original read','sources':[p['page_id']]}]
        return v
    r=run(state,s,parts,settings,b,provider)
    assert r['coverage']['scope_review']=='unresolved'
    assert r['coverage']['target_complete'] is False and r['coverage']['unresolved_count']>0
    assert r['coverage']['scope_issues']


@pytest.mark.parametrize('key',['intent_sufficient','conditions_preserved'])
def test_typed_axes_reject_legacy_negative_semantic_fields(tmp_path,key):
    def provider(req):v=typed(req);v['result'][key]=False;return v
    assert execute_review(request(),provider,budget(tmp_path),source_current=lambda:True,authorize_request=None)['status']=='rejected'


@pytest.mark.parametrize('change',['scope','read_ids','axes','context'])
def test_response_contract_failure_is_local_and_preserves_valid_source_candidates(tmp_path,change):
    state,store,s,_,settings,b=setup(tmp_path);calls=[];base=axes_provider(calls,scope='resolved')
    def provider(req):
        v=base(req)
        if req['stage']=='leaf' and len([c for c in calls if c['stage']=='leaf'])==1:
            if change=='scope':v['result'].pop('accepted_scope')
            if change=='read_ids':v['result']['read_ids']=[]
            if change=='axes':v['result']['review_axes']={}
            if change=='context':v['result']['context_requests']=[{'span_ids':['unbound'],'missing_fields':['identity']}]
        return v
    r=run(state,s,partition_snapshot(s,capacity=12),settings,b,provider)
    graph=HierarchicalStore(state/'hierarchical/graphs.sqlite3',readonly=True).load_current(s['scope'],s['permission'])['graph']
    assert len([c for c in calls if c['stage']=='extract'])>=2 and r['coverage']['leaf_count']>0
    assert graph['candidate_atoms'] and graph['leaf_failures'] and not r['coverage']['target_complete']


def test_contextual_veto_propagates_and_preserves_actual_attempt_accounting(tmp_path):
    state,snap,part,binding,limits,b,unused=context_fixture(tmp_path)
    original=execute_review(build_review_request('leaf',binding,{'partition':part,'proposal':{},'case':'scope'},limits),
        lambda p:typed(p,scope='needs_context'),b,source_current=lambda:True,authorize_request=None)
    executor=ReviewExecutor(binding,limits,state/'hierarchical',lambda p:typed(p,attribution='defective'),b,lambda:True,None,lambda p:True)
    with pytest.raises(ValueError) as caught:
        recover(snap,part,{},original,executor=executor,root=state,permission_getter=lambda:snap['permission'],provider=typed,limits=limits)
    detail=caught.value.context_recovery
    assert detail['model_context_rounds']==1 and detail['review_attempts']==1
    assert executor.calls==1 and b.status()['requests_used']==3


def test_context_neighbors_are_nearest_and_delivered_in_original_chronology(tmp_path):
    root,path,raw=source(tmp_path,text='给他们写草稿，不要发布。');rows=[json.loads(x) for x in raw.splitlines()]
    def msg(text):return {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':text}]}}
    rows[2:2]=[msg('最早：项目甲。'),msg('中间：项目乙。'),msg('最近：项目丙。')];rows.insert(6,msg('紧随澄清：他们是项目丁。'))
    path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
    state=tmp_path/'state';result=process_coverage_job(job(),root,{},store_root=state)
    snap=CoverageStore(state/'coverage.sqlite3',readonly=True).read(result['snapshot_id'])
    part={'partition_id':'target','primary':[next(s for p in partition_snapshot(snap,capacity=1000)['partitions'] for s in p['primary'] if '给他们' in s['text'])],'context_only':''}
    binding={k:snap[k] for k in ('snapshot_id','generation','scope','permission','selection_version','normalization_version')};binding['protocol']='hierarchical_review.v1'
    limits={'partition_input_tokens':20000,'partition_output_tokens':2000};b=budget(tmp_path/'budget',5)
    ask=lambda req:typed(req,attribution='needs_context',scope='needs_context')
    review=execute_review(build_review_request('leaf',binding,{'partition':part,'proposal':{}},limits),ask,b,source_current=lambda:True,authorize_request=None)
    def executor(stage,inputs):return execute_review(build_review_request(stage,binding,inputs,limits),ask,b,source_current=lambda:True,authorize_request=None)
    out=recover(snap,part,{},review,executor=executor,root=state,permission_getter=lambda:snap['permission'],provider=typed,limits=limits)
    assert [p['text'] for p in out['pages']]==['最近：项目丙。','紧随澄清：他们是项目丁。']
    assert [p['sequence'] for p in out['pages']]==sorted(p['sequence'] for p in out['pages'])
    assert [p['relative_to_primary'] for p in out['pages']]==['before','after']


def test_legacy_success_does_not_create_new_scope_evidence(tmp_path):
    state,store,s,parts,settings,b=setup(tmp_path)
    base=controlled([])
    from test_scenario_hierarchical_review import accepted
    def provider(req):return accepted(req) if req['stage']=='leaf' else base(req)
    r=run(state,s,parts,settings,b,provider)
    assert r['coverage']['scope_review']=='not_reviewed'
    assert r['coverage']['scope_axes_complete'] is False


def test_model_wire_omits_unverifiable_hash_metadata_not_original_text_or_order():
    from lib.scenario_coverage_provider import ConfiguredCoverageProvider
    span={'span_id':'source','unit_id':'u:'+('a'*64),'raw_line_sha256':'b'*64,'text_sha256':'c'*64,
        'role':'user','sequence':12,'start':0,'end':12,'text':'Only草稿🙂，不要发布。'}
    req=build_review_request('extract',{'protocol':'hierarchical_review.v1','snapshot_id':'s'},{'partition':{'primary':[span],'context_only':''}},
        {'partition_input_tokens':6000,'partition_output_tokens':2000})
    p=ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid','EVOLVING_PROFILE_API_LLM_API_KEY':'not-real'})
    wire=p.request_envelope(req);view=json.loads(wire['messages'][1]['content'])['inputs']['partition']['primary'][0]
    assert view['text']==span['text'] and view['role']=='user' and view['sequence']==12
    assert view['start']==0 and view['end']==12
    assert 'raw_line_sha256' not in view and 'text_sha256' not in view and 'unit_id' not in view
    assert req['inputs']['partition']['primary'][0]==span


def test_output_capacity_reserves_typed_axes_not_only_legacy_boolean():
    from lib.scenario_hierarchical_transport import fits_request
    req=build_review_request('merge',{}, {'atoms':[],'obligations':[]},
        {'partition_input_tokens':10000,'partition_output_tokens':300})
    assert fits_request(req,lambda p:None) is False
