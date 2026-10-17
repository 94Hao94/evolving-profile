from lib.scenario_coverage_incremental import process_coverage_job
from test_scenario_source_codec import source
from test_scenario_coverage_incremental import job
from test_scenario_coverage_end_to_end import controlled_provider


def test_transport_fallback_is_a_separately_reserved_request_not_free_retry(tmp_path):
    root,_,_=source(tmp_path);calls=[];good=controlled_provider([])
    class Backup:
        review_identity={'model':'backup','transport':'fixture'}
        def __call__(self,payload):calls.append('backup');return good(payload)
    class Primary:
        review_identity={'model':'primary','transport':'fixture'}
        def fallback_providers(self):return [Backup()]
        def __call__(self,payload):calls.append('primary');raise TimeoutError()
    result=process_coverage_job(job(),root,{'mode':'assisted','model_trial':True},store_root=tmp_path/'state',provider=Primary())
    assert calls==['primary','backup']
    assert result['model_calls']==2 and result['published'] is False
    assert result['budget']['unknown_usage_requests']==1 and result['budget']['requests_used']==2


def test_semantic_rejection_never_fishes_for_acceptance_from_fallback(tmp_path):
    root,_,_=source(tmp_path);calls=[];good=controlled_provider([])
    class Backup:
        def __call__(self,payload):calls.append('backup');return good(payload)
    class Primary:
        def fallback_providers(self):return [Backup()]
        def __call__(self,payload):
            calls.append('primary');response=good(payload);response['result']['accept']=False;return response
    result=process_coverage_job(job(),root,{'mode':'assisted','model_trial':True},store_root=tmp_path/'state',provider=Primary())
    assert calls==['primary'] and result['published'] is False


def test_explicit_rerun_of_transport_failure_uses_only_remaining_allowance(tmp_path):
    root,_,_=source(tmp_path);calls=[];good=controlled_provider([])
    class Provider:
        review_identity={'model':'fixed-profile','transport':'fixture'}
        def __call__(self,payload):
            calls.append(payload)
            if len(calls)==1:raise TimeoutError()
            return good(payload)
    provider=Provider();settings={'mode':'assisted','model_trial':True};state=tmp_path/'state'
    first=process_coverage_job(job(),root,settings,store_root=state,provider=provider)
    second=process_coverage_job(job(),root,settings,store_root=state,provider=provider)
    assert first['model_calls']==1 and second['model_calls']==1 and len(calls)==2
    assert second['budget']['requests_used']==2 and second['budget']['unknown_usage_requests']==1
