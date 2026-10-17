import json
from pathlib import Path
import pytest
from test_scenario_source_codec import source
from test_scenario_coverage_incremental import job
from lib.scenario_coverage_incremental import process_coverage_job
from lib.scenario_coverage_store import CoverageStore
from lib.scenario_coverage_partition import partition_snapshot
from lib.scenario_coverage_budget import CoverageBudget
from lib.scenario_hierarchical_review import build_review_request,execute_review
from lib.scenario_hierarchical_incremental import rebind_unchanged_leaf
from test_scenario_review_axes import typed


def context_fixture(tmp_path,prior=True):
    root,path,raw=source(tmp_path,text='给他们写草稿，不要发布。')
    if prior:
        rows=[json.loads(x) for x in raw.splitlines()]
        rows.insert(2,{'type':'response_item','payload':{'type':'message','role':'user',
            'content':[{'type':'input_text','text':'这里的对象仅是项目甲，不涉及项目乙。'}]}})
        path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
    state=tmp_path/'state';r=process_coverage_job(job(),root,{},store_root=state)
    snap=CoverageStore(state/'coverage.sqlite3',readonly=True).read(r['snapshot_id'])
    primary=next(s for p in partition_snapshot(snap,capacity=1000)['partitions'] for s in p['primary']
        if s['role']=='user' and '给他们' in s['text'])
    part={'partition_id':'target','primary':[primary],'context_only':''}
    binding={k:snap[k] for k in ('snapshot_id','generation','scope','permission','selection_version','normalization_version')}
    binding['protocol']='hierarchical_review.v1'
    limits={'partition_input_tokens':20000,'partition_output_tokens':2000}
    b=CoverageBudget(state/'context-requests.sqlite3',job_id='context-test',budget_identity='frozen',parent_attempts=0,max_requests=5,max_tokens=100000)
    req=build_review_request('leaf',binding,{'partition':part,'proposal':{}},limits)
    review=execute_review(req,lambda p:typed(p,attribution='needs_context',scope='needs_context'),b,source_current=lambda:True,authorize_request=None)
    return state,snap,part,binding,limits,b,review


def recover(*args,**kwargs):
    from lib.scenario_hierarchical_context import recover_leaf_context
    return recover_leaf_context(*args,**kwargs)


def test_recovery_reads_original_neighbor_before_repeating_leaf_not_summary(tmp_path):
    state,snap,part,binding,limits,b,review=context_fixture(tmp_path);calls=[]
    def executor(stage,inputs):
        calls.append(inputs);req=build_review_request(stage,binding,inputs,limits)
        return execute_review(req,typed,b,source_current=lambda:True,authorize_request=None)
    out=recover(snap,part,{},review,executor=executor,root=state,permission_getter=lambda:snap['permission'],provider=typed,limits=limits)
    assert out['review']['status']=='reviewed' and len(calls)==1
    assert calls[0]['context_pages'][0]['text']=='这里的对象仅是项目甲，不涉及项目乙。'
    assert calls[0]['context_pages'][0]['role']=='user'
    assert out['model_context_rounds']==1 and out['stop_reason']=='resolved'
    assert b.status()['requests_used']==2


def test_no_other_original_context_never_repeats_or_claims_resolved(tmp_path):
    state,snap,part,binding,limits,b,review=context_fixture(tmp_path,prior=False)
    part['primary']+=next(p['primary'][1:] for p in partition_snapshot(snap,capacity=1000)['partitions'])
    calls=[]
    out=recover(snap,part,{},review,executor=lambda *x:calls.append(x),root=state,
        permission_getter=lambda:snap['permission'],provider=typed,limits=limits)
    assert calls==[] and out['model_context_rounds']==0
    assert out['stop_reason']=='context_unavailable' and out['review']['status']=='needs_context'


def test_context_recovery_refuses_changed_permission_before_read_or_dispatch(tmp_path):
    state,snap,part,binding,limits,b,review=context_fixture(tmp_path);calls=[]
    with pytest.raises(ValueError):recover(snap,part,{},review,executor=lambda *x:calls.append(x),root=state,
        permission_getter=lambda:{'allowed':False,'version':'changed'},provider=typed,limits=limits)
    assert calls==[]


def test_contextual_leaf_is_not_rebound_using_only_unchanged_primary(tmp_path):
    state,snap,part,binding,limits,b,review=context_fixture(tmp_path)
    request=build_review_request('leaf',binding,{'partition':part,'proposal':{},'context_pages':[{'page_id':'p','text':'旧上下文'}]},limits)
    r=execute_review(request,typed,b,source_current=lambda:True,authorize_request=None)
    assert rebind_unchanged_leaf(r,binding,{'partition':part,'units':snap['units']}) is None


def test_context_units_and_rounds_are_bounded_even_when_model_keeps_asking(tmp_path):
    state,snap,part,binding,limits,b,review=context_fixture(tmp_path);calls=[]
    def executor(stage,inputs):
        calls.append(inputs)
        return execute_review(build_review_request(stage,binding,inputs,limits),
            lambda p:typed(p,attribution='needs_context',scope='needs_context'),b,source_current=lambda:True,authorize_request=None)
    out=recover(snap,part,{},review,executor=executor,root=state,permission_getter=lambda:snap['permission'],provider=typed,limits=limits)
    assert len(calls)<=2 and len({p['unit_id'] for p in out['pages']})<=3
    assert out['stop_reason'] in {'context_unavailable','context_round_limit'}
    assert out['review']['status']=='needs_context'


def test_additional_context_does_not_label_unresolved_scope_as_resolved(tmp_path):
    state,snap,part,binding,limits,b,review=context_fixture(tmp_path)
    def executor(stage,inputs):
        return execute_review(build_review_request(stage,binding,inputs,limits),lambda p:typed(p,scope='unresolved'),b,
            source_current=lambda:True,authorize_request=None)
    out=recover(snap,part,{},review,executor=executor,root=state,permission_getter=lambda:snap['permission'],provider=typed,limits=limits)
    assert out['stop_reason']=='review_completed_scope_unresolved'


def test_extraction_context_request_is_used_before_first_target_leaf(tmp_path):
    from lib.scenario_coverage_contract import validate_settings
    from lib.scenario_hierarchical_incremental import process_hierarchical_stages,authorize_evaluation
    from test_scenario_hierarchical_end_to_end import controlled
    state,snap,part,binding,limits,b,review=context_fixture(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        value=base(req);target=any('给他们' in s['text'] for s in req['inputs'].get('partition',{}).get('primary',[]))
        v=typed(req,scope='needs_context' if req['stage']=='extract' and target else 'resolved')
        if req['stage']=='extract':v['result']['proposal']=value['result']['proposal']
        if req['model_request'].get('wire_contract'):v['result']['wire_schema']=req['model_request']['wire_contract']
        if req['stage'] in {'merge','readback'}:v['result'].update(discovery_complete=True,relations=[],record_obligations=[],states=[])
        return v
    settings=validate_settings({'mode':'assisted','model_trial':True,'review_protocol':'hierarchical_review.v1'})
    settings['limits'].update(limits)
    process_hierarchical_stages(job(),snap,partition_snapshot(snap,capacity=60),settings,root=state,provider=provider,budget=b,
        permission_getter=lambda:snap['permission'],scope_getter=lambda:snap['scope'],authorize_request=None,parent_lease_valid=None,
        evaluation_authorization=authorize_evaluation(snap,b,'pre-leaf-context'))
    leaves=[r for r in calls if r['stage']=='leaf' and any('给他们' in s['text'] for s in r['inputs']['partition']['primary'])]
    assert leaves and leaves[0]['inputs'].get('context_pages')
    assert '项目甲' in leaves[0]['inputs']['context_pages'][0]['text']
