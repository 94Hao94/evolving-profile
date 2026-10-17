import pytest
from lib.scenario_coverage_contract import validate_settings,canonical
from lib.scenario_hierarchical_capacity import prepare_review_work
from lib.scenario_coverage_partition import validate_partition
from test_scenario_review_capacity_adaptation import provider
from test_scenario_coverage_partition import snapshot


def test_new_protocol_has_room_for_source_and_proposal_without_changing_legacy_or_explicit_lower_bound():
    assert validate_settings()['limits']['partition_input_tokens']==6000
    new=validate_settings({'review_protocol':'hierarchical_review.v1'})['limits']
    assert new['partition_input_tokens']==12000 and new['partition_output_tokens']==2000
    assert validate_settings({'review_protocol':'hierarchical_review.v1','limits':{'partition_input_tokens':6000}})['limits']['partition_input_tokens']==6000
    with pytest.raises(ValueError):validate_settings({'limits':{'partition_input_tokens':12000}})
    with pytest.raises(ValueError):validate_settings({'review_protocol':'hierarchical_review.v1','limits':{'partition_input_tokens':12001}})


def test_more_review_envelope_room_does_not_enlarge_raw_source_windows_or_lose_source(tmp_path):
    s=snapshot(tmp_path,'复杂源文🙂。'*900);limits=validate_settings({'review_protocol':'hierarchical_review.v1'})['limits']
    work=prepare_review_work(s,limits,provider())
    assert validate_partition(work['partitions'],s)['complete']
    assert all(sum(len(r['text'].encode()) for r in p['primary'])<=2000 for p in work['partitions']['partitions'])
