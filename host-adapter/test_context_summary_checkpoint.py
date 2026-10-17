"""Exercise checkpoint reuse through the real background stage orchestration."""
import copy,json
import pytest
from lib.context_incremental import ContextIncremental,process_summary
from lib import scenario_model,memory_recovery_scenario
from test_memory_recovery_scenario import fixture,response_with_intents,response_opener

CONFIG={'EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid',
        'EVOLVING_PROFILE_API_LLM_API_KEY':'private-integration-key',
        'EVOLVING_PROFILE_API_LLM_MODEL':'fixture'}

def stages(monkeypatch,source,bundle,review,*,refuse_once=False,timeout_once=False):
    calls={'generate':0,'review':0,'coverage':0}
    original=memory_recovery_scenario.request_source_coverage_review
    def generate(actual,**_):calls['generate']+=1;assert actual==source;return copy.deepcopy(bundle)
    def episode_review(actual,generated,**_):
        calls['review']+=1
        if timeout_once and calls['review']==1:raise TimeoutError('transport unavailable')
        assert actual==source and generated==bundle
        return copy.deepcopy(review)
    def coverage(actual,generated,**params):
        calls['coverage']+=1
        if refuse_once and calls['coverage']==1:raise memory_recovery_scenario.CoverageError('semantic_coverage_rejected')
        return original(actual,generated,**params,opener=response_opener(response_with_intents(source,bundle)))
    monkeypatch.setattr(scenario_model,'request_episode_bundle',generate)
    monkeypatch.setattr(scenario_model,'request_episode_bundle_review',episode_review)
    monkeypatch.setattr(memory_recovery_scenario,'request_source_coverage_review',coverage)
    return calls

def test_background_retry_reuses_generated_bundle_but_reexecutes_all_reviews(tmp_path,monkeypatch):
    root,_,source,bundle,review=fixture(tmp_path)
    calls=stages(monkeypatch,source,bundle,review,timeout_once=True)
    worker=ContextIncremental(tmp_path/'state',root,debounce=0,bank_id='bank')
    worker.discover(now=100)
    original=dict(CONFIG)
    first=worker.run_once(CONFIG,now=101)
    assert first['status']=='retrying'
    second=worker.run_once(CONFIG,now=200)
    assert second['status']=='complete'
    assert calls=={'generate':1,'review':2,'coverage':1}
    assert CONFIG==original
    with worker.db() as db:
        job=dict(db.execute('SELECT * FROM jobs').fetchone())
    assert job['attempts']==2
    files=list((worker.root/'summary-checkpoints').rglob('*.json'))
    assert files
    assert all(CONFIG['EVOLVING_PROFILE_API_LLM_API_KEY'] not in path.read_text() for path in files)

def test_rejected_coverage_invalidates_bundle_and_does_not_reuse_semantic_failure(tmp_path,monkeypatch):
    root,_,source,bundle,review=fixture(tmp_path)
    calls=stages(monkeypatch,source,bundle,review,refuse_once=True)
    config={**CONFIG,'_scenario_checkpoint_root':tmp_path/'checkpoints'}
    with pytest.raises(memory_recovery_scenario.CoverageError,match='automated_source_coverage_incomplete'):
        process_summary(source,{},root,config)
    assert len(list((tmp_path/'checkpoints').rglob('*.json')))>=2
    index=next((tmp_path/'checkpoints').rglob('index.json'))
    assert json.loads(index.read_text())['status']=='invalidated'
    result=process_summary(source,{},root,config)
    assert result['status']=='episode_directory_ready'
    assert calls=={'generate':2,'review':2,'coverage':2}

def test_direct_processor_without_checkpoint_keeps_existing_no_disk_contract(tmp_path,monkeypatch):
    root,_,source,bundle,review=fixture(tmp_path)
    calls=stages(monkeypatch,source,bundle,review)
    assert process_summary(source,{},root,CONFIG)['status']=='episode_directory_ready'
    assert calls=={'generate':1,'review':1,'coverage':1}
    assert not list(tmp_path.rglob('index.json'))
