from concurrent.futures import ThreadPoolExecutor
import pytest
from lib.scenario_coverage_budget import CoverageBudget


def test_default_zero_and_parent_exhaustion_prevent_reservation(tmp_path):
    ledger=CoverageBudget(tmp_path/'b.sqlite',job_id='j',budget_identity='semantic',parent_attempts=1)
    with pytest.raises(ValueError,match='budget_paused'):ledger.reserve_request('local','input',100)
    spent=CoverageBudget(tmp_path/'b.sqlite',job_id='spent',budget_identity='semantic2',parent_attempts=3,max_requests=2,max_tokens=1000)
    with pytest.raises(ValueError,match='parent_attempts_exhausted'):spent.reserve_request('local','input',100)


def test_restart_provider_or_identity_cannot_refresh_original_budget(tmp_path):
    path=tmp_path/'b.sqlite'
    one=CoverageBudget(path,job_id='j',budget_identity='semantic',parent_attempts=1,max_requests=1,max_tokens=300)
    reservation=one.reserve_request('local','input',200)
    one.settle_request(reservation,None,response_fingerprint=None)
    two=CoverageBudget(path,job_id='j',budget_identity='semantic',parent_attempts=0,max_requests=100,max_tokens=100000)
    with pytest.raises(ValueError,match='budget_paused'):two.reserve_request('other-provider','new',1)
    state=two.status()
    assert state['requests_used']==1 and state['charged_tokens']==200 and state['unknown_usage_requests']==1
    with pytest.raises(ValueError,match='budget_identity_changed'):
        CoverageBudget(path,job_id='j',budget_identity='different',parent_attempts=1,max_requests=2,max_tokens=500)
    with pytest.raises(ValueError,match='already_settled'):two.settle_request(reservation,{'total_tokens':1},response_fingerprint='abc')


def test_concurrent_reservations_respect_combined_ceiling(tmp_path):
    ledger=CoverageBudget(tmp_path/'b.sqlite',job_id='j',budget_identity='semantic',parent_attempts=1,max_requests=2,max_tokens=300)
    def reserve(i):
        try:return ledger.reserve_request('local',str(i),200)['status']
        except ValueError:return 'paused'
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(reserve,range(2)))
    assert sorted(results)==['paused','reserved']
    assert ledger.status()['charged_tokens']==200


def test_new_generation_uses_only_original_unspent_budget_and_owner(tmp_path):
    path=tmp_path/'b.sqlite'
    old=CoverageBudget(path,job_id='j',budget_identity='old',parent_attempts=1,max_requests=2,max_tokens=300,scope_identity='scope1')
    r=old.reserve_request('local','old-input',150);old.settle_request(r,{'total_tokens':100},response_fingerprint='response1')
    newer=CoverageBudget.continue_generation(path,job_id='j',scope_identity='scope1',parent_attempts=2)
    assert newer.status()['identity']=='old' and newer.status()['requests_used']==1
    r2=newer.reserve_request('local','new-generation',150);newer.settle_request(r2,None,response_fingerprint=None)
    assert newer.status()['requests_used']==2 and newer.status()['max_requests']==2
    with pytest.raises(ValueError,match='budget_paused'):newer.reserve_request('global','another',1)
    with pytest.raises(ValueError,match='budget_scope_changed'):
        CoverageBudget.continue_generation(path,job_id='j',scope_identity='scope2',parent_attempts=1)
