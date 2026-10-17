import copy
from lib.scenario_coverage_partition import partition_snapshot,build_requirement_catalog
from lib.scenario_global_review import plan_global_review,validate_global_coverage
from test_scenario_coverage_partition import snapshot


def test_local_green_without_global_parts_is_still_partial(tmp_path):
    snap=snapshot(tmp_path,'不要发布。'*30);parts=partition_snapshot(snap,capacity=80)
    ledger={'partition_plan':parts,'requirements':build_requirement_catalog(parts),'local_reviews':[]}
    plan=plan_global_review(snap,ledger)
    result=validate_global_coverage(plan,[],ledger)
    assert result['status']=='partial' and result['overall_complete'] is False
    assert result['missing_part_ids']


def test_all_cross_partition_edges_required_not_just_adjacent_top_k():
    requirements=[{'requirement_id':str(i),'text':str(i),'partition_ids':[str(i)],'snapshot_id':'s','unit_id':str(i),'sequence':i} for i in range(4)]
    ledger={'requirements':{'snapshot_id':'s','requirements':requirements},'local_reviews':[],'partition_plan':{'partitions':[]}}
    plan=plan_global_review({'snapshot_id':'s','generation':1},ledger)
    assert len(plan['required_edges'])==6
    assert any(e['from']=='0' and e['to']=='3' for e in plan['required_edges'])
    assert validate_global_coverage(plan,[],ledger)['status']=='partial'


def test_remote_correction_requires_later_user_source_and_global_receipt():
    from lib.scenario_global_review import validate_relation
    req=[{'requirement_id':'a','text':'发布版本A。','sequence':1,'role':'user','snapshot_id':'s'},
         {'requirement_id':'b','text':'不要发布A，改为B。','sequence':30,'role':'user','snapshot_id':'s'}]
    relation={'type':'supersedes','from':'b','to':'a','evidence_quote':'不要发布A，改为B。','evidence_kind':'explicit_user_correction'}
    assert validate_relation(relation,req) is True
    bad=copy.deepcopy(relation);bad['from']='a';bad['to']='b'
    assert not validate_relation(bad,req)
    req[1]['role']='assistant'
    assert not validate_relation(relation,req)
