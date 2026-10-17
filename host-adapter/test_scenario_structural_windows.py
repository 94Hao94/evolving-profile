from lib.scenario_coverage_partition import partition_snapshot,validate_partition
from lib.scenario_hierarchical_capacity import prepare_review_work
from lib.scenario_coverage_contract import validate_settings
from test_scenario_coverage_partition import snapshot
from test_scenario_review_capacity_adaptation import provider


def test_hierarchical_windows_prefer_complete_paragraphs_without_changing_default(tmp_path):
    text=('先检查原件，不要发布。\n\n'*45)+'Last condition: do not overwrite. 🙂'
    s=snapshot(tmp_path,text)
    default=partition_snapshot(s,capacity=96,context_tokens=8)
    chosen=partition_snapshot(s,capacity=96,context_tokens=8,prefer_boundaries=True)
    assert default['partitions'][0]['primary'][0]['text']!=chosen['partitions'][0]['primary'][0]['text']
    spans=[span for p in chosen['partitions'] for span in p['primary'] if span['role']=='user']
    assert spans[0]['text']=='先检查原件，不要发布。\n\n'*2
    assert ''.join(x['text'] for x in spans)==text and validate_partition(chosen,s)['complete']
    assert all(len(x['text'].encode())<=96 for x in spans)
    assert all(p['semantic_task_boundary']=='unknown' for p in chosen['partitions'])


def test_unbroken_code_path_and_multibyte_text_still_cover_every_character(tmp_path):
    text='a:/opaque_path_🙂字'*100
    s=snapshot(tmp_path,text);p=partition_snapshot(s,capacity=37,prefer_boundaries=True)
    assert validate_partition(p,s)['complete']
    spans=[x for part in p['partitions'] for x in part['primary'] if x['role']=='user']
    assert ''.join(x['text'] for x in spans)==text
    assert all(len(x['text'].encode())<=37 for x in spans)


def test_hierarchical_execution_reproduces_preferred_original_windows(tmp_path):
    s=snapshot(tmp_path,'原文条件不得删除。\n\n'*120);limits=validate_settings()['limits'];p=provider()
    a=prepare_review_work(s,limits,p);b=prepare_review_work(s,limits,p,a['source_partitions'])
    assert a['partitions']==b['partitions'] and a['plan']==b['plan']
    assert a['partitions']['boundary_preference']=='structural_not_semantic'
