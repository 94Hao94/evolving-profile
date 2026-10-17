import pytest
from lib.scenario_coverage_publish import publish_segmented_navigation
from lib.scenario_coverage_store import CoverageStore
from test_scenario_coverage_partition import snapshot


def test_partial_or_unreviewed_structure_cannot_replace_existing_navigation(tmp_path):
    snap=snapshot(tmp_path,'只检查，不发布。')
    with pytest.raises(ValueError,match='coverage_not_accepted'):
        publish_segmented_navigation(snap,{}, {'status':'partial'},expected_generation=snap['generation'])
    with pytest.raises(ValueError,match='coverage_not_accepted'):
        publish_segmented_navigation(snap,{}, {'status':'accepted','overall_complete':True},expected_generation=snap['generation'])


def test_old_v3_schema_cannot_be_marked_segmented_acceptance(tmp_path):
    snap=snapshot(tmp_path,'必须保留来源。')
    with pytest.raises(ValueError):
        publish_segmented_navigation(snap,{'schema':'scenario-summary.v3'}, {},expected_generation=0)
