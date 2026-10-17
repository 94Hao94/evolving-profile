from lib.scenario_recovery_readiness import recovery_readiness


def test_failure_types_do_not_turn_into_a_generic_retry_or_budget_reset():
    exhausted=recovery_readiness({'status':'failed','attempts':3,'error_code':'scenario_source_revision_mismatch'})
    assert exhausted['action']=='new_authorization_required' and exhausted['remaining_original_attempts']==0
    capacity=recovery_readiness({'status':'waiting_source','attempts':2,'error_code':'automated_source_coverage_budget_exceeded'})
    assert capacity['action']=='segmented_review_required' and capacity['remaining_original_attempts']==1
    assert capacity['automatic_retry_allowed'] is False
    assert recovery_readiness({'status':'protected','attempts':0})['action']=='preserve_protection'
    assert recovery_readiness({'status':'waiting_source','attempts':1,'error_code':'scenario_source_empty'})['action']=='wait_for_source'


def test_missing_or_malformed_attempts_are_unknown_not_free_allowance():
    for value in [None,-1,True,'0']:
        out=recovery_readiness({'status':'failed','attempts':value})
        assert out['remaining_original_attempts'] is None and not out['automatic_retry_allowed']


def test_only_already_retrying_transport_failure_has_an_existing_automatic_route():
    out=recovery_readiness({'status':'retrying','attempts':1,'error_code':'scenario_provider_unavailable'})
    assert out['action']=='existing_bounded_transport_retry' and out['automatic_retry_allowed'] is True
    assert recovery_readiness({'status':'failed','attempts':1,'error_code':'semantic_rejected'})['automatic_retry_allowed'] is False
