import pytest
from lib.scenario_coverage_contract import validate_settings, contract


def test_default_protocol_preserves_legacy():
    value=validate_settings({})
    assert value.get('review_protocol')=='segment_coverage.v1'
    assert value['mode']=='source_shadow' and value['limits']['model_requests']==0


def test_hierarchical_shadow_cannot_claim_money_or_enforced_readiness():
    value=validate_settings({'review_protocol':'hierarchical_review.v1','model_trial':True})
    assert value['limits']['model_requests']==0
    with pytest.raises(ValueError):
        validate_settings({'review_protocol':'hierarchical_review.v1','mode':'enforced'})
    with pytest.raises(ValueError):validate_settings({'review_protocol':'unknown'})
    assert contract()['review_protocols']['hierarchical_review.v1']['exhaustive'] is False
