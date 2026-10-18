import copy

from lib.scenario_coverage_partition import partition_snapshot, validate_partition, build_requirement_catalog
from lib.scenario_coverage_store import CoverageStore,freeze_snapshot
from lib.scenario_source_codec import locate_source,open_source_stream,read_source_batch
from test_scenario_source_codec import SID,source


def snapshot(tmp_path,text):
    root,_,_=source(tmp_path,text=text);loc=locate_source(SID,root);p={'allowed':True,'version':'p1'}
    store=CoverageStore(tmp_path/'coverage.sqlite3');s=freeze_snapshot(loc,p);store.create_snapshot(s)
    with open_source_stream(loc,permission=lambda:True) as stream:batch=read_source_batch(stream)
    return store.append_source_batch(s['snapshot_id'],batch,expected_version=0,permission=p)


def test_unicode_long_negation_covered_once_without_task_invention(tmp_path):
    text='不要删🙂。 Do not publish. 只做检查！'*100
    s=snapshot(tmp_path,text);plan=partition_snapshot(s,capacity=100,context_tokens=12)
    assert validate_partition(plan,s)['complete'] is True
    spans=[span for part in plan['partitions'] for span in part['primary'] if span['role']=='user']
    assert ''.join(span['text'] for span in spans)==text
    assert len(spans)>3
    assert all(part['semantic_task_boundary']=='unknown' for part in plan['partitions'])
    catalog=build_requirement_catalog(plan)
    assert len(catalog['requirements'])==1
    requirement=catalog['requirements'][0]
    assert requirement['text']==text and requirement['kind']=='unclassified_user_message'
    assert requirement['status']=='unresolved' and requirement['external_fact_verified'] is False


def test_context_overlap_never_counts_as_primary_or_fills_missing_span(tmp_path):
    s=snapshot(tmp_path,'不要删除。'*80);plan=partition_snapshot(s,capacity=90,context_tokens=9)
    assert any(p['context_only'] for p in plan['partitions'][1:])
    bad=copy.deepcopy(plan);bad['partitions'][1]['primary'].pop()
    result=validate_partition(bad,s)
    assert result['complete'] is False and result['missing_units']


def test_duplicate_span_and_stale_snapshot_rejected(tmp_path):
    s=snapshot(tmp_path,'原始要求。'*50);plan=partition_snapshot(s,capacity=100)
    bad=copy.deepcopy(plan);bad['partitions'][1]['primary'].append(bad['partitions'][0]['primary'][0])
    assert not validate_partition(bad,s)['complete']
    newer=copy.deepcopy(s);newer['snapshot_id']='new'
    assert not validate_partition(plan,newer)['complete']


def test_structured_metadata_exclusion_does_not_remove_mixed_human_text(tmp_path):
    text='<external_codex_apps_open_page>{"page_id":"p1"}</external_codex_apps_open_page>\n不要发布。'
    s=snapshot(tmp_path,text);plan=partition_snapshot(s,capacity=200)
    req=build_requirement_catalog(plan)['requirements'][0]
    assert req['text']=='不要发布。'
    assert plan['exclusions'][0]['unit_id']
