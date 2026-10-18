import json
import io
import pytest
from lib.scenario_coverage_partition import partition_snapshot,validate_partition
from lib.scenario_coverage_provider import ConfiguredCoverageProvider
from test_scenario_coverage_partition import snapshot
from test_scenario_hierarchical_review import budget
from test_scenario_review_partial import run
from test_scenario_hierarchical_end_to_end import controlled,model_source_text


def test_unicode_split_replaces_only_failed_window_with_exact_union(tmp_path):
    from lib.scenario_hierarchical_output_recovery import split_failed_partition
    s=snapshot(tmp_path,'Draft🙂 不要发布，只有最终确认才可发送。'*20)
    plan=partition_snapshot(s,capacity=1800);parent=plan['partitions'][0]
    children=split_failed_partition(s,parent,depth=0,additional_windows=0)
    replaced={**plan,'partitions':children+plan['partitions'][1:]}
    assert validate_partition(replaced,s)['complete']
    assert ''.join(span['text'] for p in children for span in p['primary'])==''.join(span['text'] for span in parent['primary'])
    assert len(children)==2 and parent['partition_id'] not in [p['partition_id'] for p in children]
    assert split_failed_partition(s,parent,depth=3,additional_windows=0) is None
    assert split_failed_partition(s,parent,depth=0,additional_windows=16) is None


def test_tiny_window_cannot_enter_endless_output_recovery(tmp_path):
    from lib.scenario_hierarchical_output_recovery import split_failed_partition
    s=snapshot(tmp_path,'短文🙂');parent=partition_snapshot(s,capacity=1000)['partitions'][0]
    assert split_failed_partition(s,parent,depth=0,additional_windows=0) is None


@pytest.mark.parametrize('timeout_first',[False,True])
def test_actual_typed_truncation_can_resume_children_without_repaying_parent(tmp_path,timeout_first):
    from lib.scenario_coverage_incremental import process_coverage_job
    from lib.scenario_coverage_store import CoverageStore
    from lib.scenario_coverage_contract import validate_settings
    from lib.scenario_hierarchical_store import HierarchicalStore
    from test_scenario_source_codec import source
    from test_scenario_coverage_incremental import job
    root,_,_=source(tmp_path,text='不要发布🙂，仅检查草稿。'*22);state=tmp_path/'state'
    result=process_coverage_job(job(),root,{},store_root=state)
    s=CoverageStore(state/'coverage.sqlite3').read(result['snapshot_id'])
    parts=partition_snapshot(s,capacity=1800)
    settings=validate_settings({'mode':'assisted','model_trial':True,'review_protocol':'hierarchical_review.v1'})
    settings['limits']['partition_input_tokens']=20000;b=budget(tmp_path,requests=20);calls=[];base=controlled(calls)
    def opener(request,**_):
        wire=json.loads(request.data);p=json.loads(wire['messages'][1]['content'])
        if timeout_first and not calls:
            calls.append({'stage':'timeout'});raise TimeoutError()
        if p['stage']=='extract' and sum(len(model_source_text(p['inputs'],s).encode()) for s in p['inputs']['partition']['primary'])>500:
            calls.append({'stage':'truncated'})
            data={'choices':[{'finish_reason':'length','message':{'content':'{'}}],'usage':{'total_tokens':101}}
        else:
            response=base({'model_request':p})
            data={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(response['result'])}}],'usage':response['usage']}
        return io.BytesIO(json.dumps(data).encode())
    provider=ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid','EVOLVING_PROFILE_API_LLM_API_KEY':'test'},opener=opener)
    provider.requires_parent_lease=False  # Isolated fixture, no production parent.
    if timeout_first:
        assert run(state,s,parts,settings,b,provider)['reason']=='provider_failed'
    r=run(state,s,parts,settings,b,provider)
    assert r['status']=='scope_reviewed' and r['coverage']['target_complete'] is True
    g=HierarchicalStore(state/'hierarchical/graphs.sqlite3',readonly=True).load_current(s['scope'],s['permission'])['graph']
    assert g['output_recovery'] and g['output_recovery'][0]['failed_reservation_id']
    assert len(g['manifest']['leaf_partition_ids'])>=2
    before=len(calls);spent=b.status()['requests_used']
    again=run(state,s,parts,settings,b,provider)
    assert again['status']=='scope_reviewed' and again['model_calls']==0
    assert len(calls)==before and b.status()['requests_used']==spent


def test_cached_veto_after_transport_retry_remains_veto_on_third_resume(tmp_path):
    from lib.scenario_hierarchical_execution import ReviewExecutor
    from lib.scenario_hierarchical_review import ReviewRejected
    from test_scenario_proposal_authority import proposal_request
    req=proposal_request();b=budget(tmp_path);calls=[]
    def provider(request):
        calls.append(request)
        if len(calls)==1:raise TimeoutError()
        return {'result':{'accept':False},'usage':{'total_tokens':40}}
    def execute():
        runner=ReviewExecutor(req['binding'],req['limits'],tmp_path/'reviews',provider,b,lambda:True,None,lambda _:True)
        return runner('extract',req['inputs'])
    with pytest.raises(ValueError,match='^provider_failed$'):execute()
    for _ in range(2):
        with pytest.raises(ReviewRejected,match='^semantic_rejected$'):execute()
    assert len(calls)==2 and b.status()['requests_used']==2
    assert b.status()['unknown_usage_requests']==1


@pytest.mark.parametrize('failure',['semantic_veto','http_failure','untyped_length'])
def test_non_truncation_failures_never_split_or_mask_veto(tmp_path,failure):
    from test_scenario_hierarchical_end_to_end import setup
    state,_,s,parts,settings,b=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        if failure=='semantic_veto':
            value=base(req);value['result']['accept']=False;return value
        calls.append(req)
        if failure=='untyped_length':raise ValueError('coverage_response_incomplete')
        raise TimeoutError()
    result=run(state,s,parts,settings,b,provider)
    assert len(calls)==1 and result.get('output_recovery')==[]
    assert not result['published'] and result['coverage']['target_complete'] is False
    assert b.status()['requests_used']==1


def test_mutated_failed_cache_metadata_cannot_become_output_split_authority(tmp_path):
    from lib.scenario_hierarchical_output_recovery import output_truncated
    from lib.scenario_hierarchical_review import execute_review
    from test_scenario_proposal_authority import proposal_request
    p=ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid','EVOLVING_PROFILE_API_LLM_API_KEY':'test'},
        opener=lambda *a,**k:io.BytesIO(json.dumps({'choices':[],'usage':{'total_tokens':71}}).encode()))
    receipt=dict(execute_review(proposal_request(),p,budget(tmp_path),source_current=lambda:True,authorize_request=lambda:None))
    receipt['reason']='provider_capacity_failed'
    receipt['provider_response']['provider_failure']='coverage_response_incomplete'
    assert output_truncated(receipt,'extract') is False
