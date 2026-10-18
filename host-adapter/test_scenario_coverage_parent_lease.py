import pytest
from lib.context_incremental import ContextIncremental
from test_context_incremental import rollout,write_runtime_settings
from test_scenario_source_codec import SID


def test_paid_pilot_and_legacy_worker_share_remaining_parent_attempts(tmp_path):
    root=tmp_path/'sessions';rollout(root,SID);state=tmp_path/'state';write_runtime_settings(state)
    worker=ContextIncremental(state,root,bank_id='b');worker.discover(now=1)
    with worker.db() as db:
        db.execute("UPDATE jobs SET status='waiting_source',attempts=1,error_code='scenario_over_budget'")
        revision=db.execute('SELECT revision FROM jobs').fetchone()[0]
    lease=worker.acquire_coverage_parent_lease(SID,revision,now=10)
    assert lease['attempts']==2 and worker.coverage_parent_lease_valid(lease,now=11)
    with pytest.raises(ValueError,match='parent_job_busy'):
        worker.acquire_coverage_parent_lease(SID,revision,now=11)
    with worker.db() as db:
        db.execute("UPDATE jobs SET status='pending',due=0")
    assert worker.claim(now=12) is None
    worker.release_coverage_parent_lease(lease)
    assert worker.claim(now=13)['attempts']==3


def test_exhausted_or_active_legacy_job_cannot_start_extra_model_pilot(tmp_path):
    root=tmp_path/'sessions';rollout(root,SID);state=tmp_path/'state';write_runtime_settings(state)
    worker=ContextIncremental(state,root,bank_id='b');worker.discover(now=1)
    with worker.db() as db:
        revision=db.execute('SELECT revision FROM jobs').fetchone()[0]
    with pytest.raises(ValueError,match='parent_job_busy'):
        worker.acquire_coverage_parent_lease(SID,revision,now=2)
    with worker.db() as db:db.execute("UPDATE jobs SET status='failed',attempts=3")
    with pytest.raises(ValueError,match='parent_attempts_exhausted'):
        worker.acquire_coverage_parent_lease(SID,revision,now=3)


def test_actual_worker_consumes_one_attempt_only_for_new_requests_not_cache(tmp_path):
    from test_scenario_coverage_end_to_end import controlled_provider
    root=tmp_path/'sessions';rollout(root,SID);state=tmp_path/'state';write_runtime_settings(state)
    worker=ContextIncremental(state,root,bank_id='b');worker.discover(now=1)
    with worker.db() as db:db.execute("UPDATE jobs SET status='waiting_source',attempts=1")
    calls=[];settings={'mode':'assisted','model_trial':True}
    first=worker.process_coverage(SID,settings,provider=controlled_provider(calls))
    assert first['published'] and first['model_calls']==2 and first['attempts']==2
    second=worker.process_coverage(SID,settings,provider=controlled_provider(calls))
    assert second['published'] and second['model_calls']==0 and len(calls)==2
    with worker.db() as db:
        row=db.execute('SELECT attempts,status FROM jobs').fetchone()
        assert tuple(row)==(2,'waiting_source')
        assert db.execute('SELECT count(*) FROM coverage_parent_leases').fetchone()[0]==0


def test_active_legacy_parent_denial_does_not_spend_model_allowance(tmp_path):
    from test_scenario_coverage_end_to_end import controlled_provider
    root=tmp_path/'sessions';rollout(root,SID);state=tmp_path/'state';write_runtime_settings(state)
    worker=ContextIncremental(state,root,bank_id='b');worker.discover(now=1)
    calls=[];result=worker.process_coverage(SID,{'mode':'assisted','model_trial':True},provider=controlled_provider(calls))
    assert result['reason']=='parent_job_busy' and result['model_calls']==0 and calls==[]
    assert result['budget']['requests_used']==0
