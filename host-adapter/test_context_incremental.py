import json
import uuid
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from lib.context_summary import read_context_index


def write_runtime_settings(state_root, override=None):
    """Write the minimal runtime-settings fixture shared by context tests."""
    settings = {
        'generation': 1,
        'routing': {'ep_enabled': True},
        'modules': {'scenario_summary': {'record': True}},
    }

    def merge(target, extra):
        for key, value in (extra or {}).items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = value

    merge(settings, override or {})
    path = Path(state_root) / 'config/runtime-settings.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False))
    return path


def rollout(root, sid, text='Review the deployment gap', cwd='/workspace/demo', created_at='2026-10-08T01:00:00Z'):
    root.mkdir(parents=True, exist_ok=True)
    path = root / f'rollout-2026-10-08-{sid}.jsonl'
    rows = [
        {'type': 'session_meta', 'timestamp':created_at, 'payload': {'id': sid, 'cwd': cwd, 'timestamp':created_at}},
        {'type': 'turn_context', 'payload': {'turn_id': 't1', 'model': 'actual-model', 'cwd': cwd}},
        {'type': 'response_item', 'timestamp': '2026-10-08T01:00:00Z', 'payload': {
            'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': text}]}},
    ]
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    return path


def test_discovery_is_debounced_bounded_and_updates_navigation_without_model(tmp_path):
    from lib.context_incremental import ContextIncremental
    root = tmp_path / 'sessions'
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for sid in ids: rollout(root, sid)
    pipeline = ContextIncremental(tmp_path / 'state', root)
    assert pipeline.discover(now=100, limit=2)['discovered'] == 2
    assert pipeline.claim(now=101) is None
    assert pipeline.discover(now=101, limit=2)['discovered'] == 1
    assert pipeline.progress()['pending'] == 3
    session = read_context_index(pipeline.index)['sessions'][0]
    assert session['status'] == 'raw_available_summary_pending'
    assert 'summary' not in session or not any(session['summary'].values())
    assert session['source_stat_revision']
    assert session['title'] == 'Review the deployment gap'


def test_source_changed_during_processing_supersedes_old_job_without_lost_update(tmp_path):
    from lib.context_incremental import ContextIncremental
    root = tmp_path / 'sessions'; sid = str(uuid.uuid4())
    path = rollout(root, sid)
    p = ContextIncremental(tmp_path / 'state', root)
    p.discover(now=100)
    job = p.claim(now=200)
    with path.open('a') as stream:
        stream.write(json.dumps({'type': 'event_msg', 'payload': {'message': 'more'}}) + '\n')
    p.discover(now=201)
    assert p.finish(job, {'context_id': 'session:' + sid, 'session_id': sid, 'status': 'model_reviewed'}, now=202) is False
    assert p.progress()['pending'] == 1
    current = read_context_index(p.index)['sessions'][0]
    assert current['status'] == 'raw_available_summary_pending'
    assert p.claim(now=300)['revision'] != job['revision']


def test_leases_resume_after_crash_and_retry_limit_keeps_raw_available(tmp_path):
    from lib.context_incremental import ContextIncremental
    sid = str(uuid.uuid4()); rollout(tmp_path / 'sessions', sid)
    p = ContextIncremental(tmp_path / 'state', tmp_path / 'sessions')
    p.discover(now=100)
    job = p.claim(now=200)
    assert p.claim(now=201) is None
    recovered = p.claim(now=2000)
    assert recovered['session_id'] == sid
    p.fail(recovered, 'provider_unavailable', now=2001)
    last = p.claim(now=3000)
    p.fail(last, 'provider_unavailable', now=3001)
    assert p.claim(now=10000) is None
    assert p.progress()['failed'] == 1
    assert read_context_index(p.index)['sessions'][0]['status'] == 'raw_available_summary_failed'


def test_workers_claim_each_session_once_and_preserve_existing_index(tmp_path):
    from lib.context_incremental import ContextIncremental
    from lib.context_summary import write_context_index
    root = tmp_path / 'sessions'
    for _ in range(8): rollout(root, str(uuid.uuid4()))
    p = ContextIncremental(tmp_path / 'state', root)
    write_context_index(p.index, [{'session_id': 'legacy', 'context_id': 'session:legacy'}], [])
    p.discover(now=100)
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(lambda _: p.claim(now=200), range(8)))
    assert len({j['session_id'] for j in jobs}) == 8
    assert any(r['session_id'] == 'legacy' for r in read_context_index(p.index)['sessions'])


def test_worker_uses_ep_provider_and_failure_never_publishes_seed(tmp_path):
    from lib.context_incremental import ContextIncremental
    sid = str(uuid.uuid4()); rollout(tmp_path / 'sessions', sid)
    p = ContextIncremental(tmp_path / 'state', tmp_path / 'sessions')
    p.discover(now=100)
    def unavailable(source, row, session_root, config):
        assert config['EVOLVING_PROFILE_API_LLM_MODEL'] == 'ep-configured'
        raise ConnectionError('private endpoint/key must not enter progress')
    result = p.run_once({'EVOLVING_PROFILE_API_LLM_MODEL': 'ep-configured'}, now=200, processor=unavailable)
    assert result['status'] == 'retrying'
    assert 'private endpoint' not in json.dumps(p.progress())
    assert read_context_index(p.index)['sessions'][0]['status'] == 'raw_available_summary_pending'


def test_successful_processing_updates_index_and_coverage_and_preserves_model_identity(tmp_path):
    from lib.context_incremental import ContextIncremental
    sid = str(uuid.uuid4()); rollout(tmp_path / 'sessions', sid)
    p = ContextIncremental(tmp_path / 'state', tmp_path / 'sessions')
    p.discover(now=100)
    def checked(source, row, session_root, config):
        return {**row, 'status': 'model_reviewed', 'summary': {'compact': 'summary'},
                'source_revision': source['source_revision'], 'summary_model': config['EVOLVING_PROFILE_API_LLM_MODEL']}
    assert p.run_once({'EVOLVING_PROFILE_API_LLM_MODEL': 'ep-model'}, now=200, processor=checked)['status'] == 'complete'
    row = read_context_index(p.index)['sessions'][0]
    assert row['summary_kind'] == 'canonical_model_summary'
    assert row['summary_model'] == 'ep-model'
    assert p.progress()['succeeded'] == 1
    assert p.discover(now=300)['discovered'] == 0


def test_capacity_deferral_is_partial_coverage_and_eventually_discovers_unqueued_sources(tmp_path):
    from lib.context_incremental import ContextIncremental
    for _ in range(2): rollout(tmp_path / 'sessions', str(uuid.uuid4()))
    p = ContextIncremental(tmp_path / 'state', tmp_path / 'sessions', capacity=1)
    assert p.discover(now=100)['capacity_deferred'] == 1
    job = p.claim(now=200); p.fail(job, 'source_over_budget', now=201, terminal=True)
    assert p.progress()['status'] != 'complete'
    assert p.discover(now=300)['discovered'] == 1


def test_new_navigation_row_reads_raw_fallback_and_exposes_background_progress(tmp_path, monkeypatch):
    import evolving_profile_controller_mcp as mcp
    from lib.context_incremental import ContextIncremental
    sid = str(uuid.uuid4()); root = tmp_path / 'sessions'
    rollout(root, sid)
    p = ContextIncremental(tmp_path / 'state', root); p.discover(now=100)
    monkeypatch.setattr(mcp, 'CONTEXT_INDEX_PATH', p.index)
    monkeypatch.setattr(mcp, 'THREAD_SESSION_ROOT', root)
    monkeypatch.setattr(mcp, 'runtime_disabled', lambda *_: None)
    monkeypatch.setattr(mcp.Path, 'home', lambda: tmp_path)
    result = json.loads(mcp.read_context_summary({'scenario_type': 'session', 'scenario_id': 'session:' + sid})['content'][0]['text'])
    assert result['status'] == 'available_unreviewed'
    assert result['items'][0]['summary_kind'] == 'raw_message_excerpt'
    assert 'Review the deployment gap' in result['items'][0]['summary']
    assert result['summary_processing']['status'] == 'raw_available_summary_pending'
    assert result['summary_processing']['foreground_model_call'] is False


def test_cli_discovery_needs_no_provider_and_queues_without_model_requests(tmp_path):
    sid = str(uuid.uuid4()); root = tmp_path / 'sessions'; rollout(root, sid)
    settings = tmp_path/'state/config/runtime-settings.json'
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({'routing':{'ep_enabled':True},'modules':{'scenario_summary':{'record':True}}}))
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('context-incremental-worker.py')),
        '--state-root', str(tmp_path/'state'), '--session-root', str(root), '--discover-only'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt['discovery']['discovered'] == 1
    assert receipt['progress']['pending'] == 1
    assert receipt['model_calls'] == 0


def test_index_write_interruption_is_reconciled_next_discovery(tmp_path, monkeypatch):
    import lib.context_incremental as module
    sid = str(uuid.uuid4()); rollout(tmp_path/'sessions', sid)
    p = module.ContextIncremental(tmp_path/'state', tmp_path/'sessions')
    real_update = module.update_context_index
    def interrupted(*_args, **_kwargs): raise OSError('interrupted')
    monkeypatch.setattr(module, 'update_context_index', interrupted)
    with pytest.raises(OSError): p.discover(now=100)
    monkeypatch.setattr(module, 'update_context_index', real_update)
    assert p.discover(now=110)['discovered'] == 1
    assert read_context_index(p.index)['sessions'][0]['session_id'] == sid


def test_empty_queue_does_not_claim_coverage_complete_before_discovery(tmp_path):
    from lib.context_incremental import ContextIncremental
    p = ContextIncremental(tmp_path/'state', tmp_path/'sessions')
    assert p.progress()['status'] == 'not_discovered'


def test_disabled_scenario_recording_prevents_worker_discovery_and_models(tmp_path):
    sid = str(uuid.uuid4()); root = tmp_path / 'sessions'; rollout(root, sid)
    settings = tmp_path/'state/config/runtime-settings.json'; settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({'modules':{'scenario_summary':{'record':False}}}))
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('context-incremental-worker.py')),
        '--state-root', str(tmp_path/'state'), '--session-root', str(root), '--process'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['status'] == 'disabled'
    assert not (tmp_path/'state/context/context-index.json').exists()


def test_source_append_before_next_discovery_marks_old_summary_stale_and_reads_raw(tmp_path, monkeypatch):
    import evolving_profile_controller_mcp as mcp
    from lib.context_incremental import ContextIncremental
    sid = str(uuid.uuid4()); root = tmp_path/'sessions'; path = rollout(root, sid)
    p = ContextIncremental(tmp_path/'state', root); p.discover(now=100)
    p.run_once({}, now=200, processor=lambda source,row,*_: {**row, 'status':'model_reviewed','summary':{'compact':'OLD REVIEWED SUMMARY'}})
    with path.open('a') as stream:
        stream.write(json.dumps({'type':'response_item','timestamp':'2026-10-08T02:00:00Z','payload':{
            'type':'message','role':'user','content':[{'type':'input_text','text':'The deployment gap is now corrected.'}]}})+'\n')
    monkeypatch.setattr(mcp,'CONTEXT_INDEX_PATH',p.index); monkeypatch.setattr(mcp,'THREAD_SESSION_ROOT',root)
    monkeypatch.setattr(mcp,'runtime_disabled',lambda *_:None); monkeypatch.setattr(mcp.Path,'home',lambda:tmp_path)
    result = json.loads(mcp.read_context_summary({'scenario_type':'session','scenario_id':'session:'+sid})['content'][0]['text'])
    assert result['status'] == 'available_unreviewed'
    assert result['summary_processing']['status'] == 'stale_source_pending'
    assert result['items'][0]['summary_kind'] == 'raw_message_excerpt'
    assert 'OLD REVIEWED SUMMARY' not in result['items'][0]['summary']


def test_scoped_catchup_does_not_claim_other_queued_sessions(tmp_path):
    from lib.context_incremental import ContextIncremental
    ids = sorted(str(uuid.uuid4()) for _ in range(2))
    for sid in ids: rollout(tmp_path/'sessions', sid)
    all_jobs = ContextIncremental(tmp_path/'state',tmp_path/'sessions'); all_jobs.discover(now=100)
    scoped = ContextIncremental(tmp_path/'state',tmp_path/'sessions',session_ids=[ids[1]])
    assert scoped.claim(now=200)['session_id'] == ids[1]
    assert scoped.claim(now=200) is None
    assert all_jobs.claim(now=200)['session_id'] == ids[0]


def test_no_memory_write_source_remains_raw_and_never_reaches_summary_provider(tmp_path):
    from lib.context_incremental import ContextIncremental
    sid = str(uuid.uuid4()); root = tmp_path/'sessions'
    rollout(root, sid, text='不查历史，也不要修改任何配置或记忆。只改写这一句话。')
    p = ContextIncremental(tmp_path/'state',root); p.discover(now=100)
    def provider(*_): raise AssertionError('Forbidden source reached model')
    result = p.run_once({}, now=200, processor=provider)
    assert result['status'] == 'protected'
    row = read_context_index(p.index)['sessions'][0]
    assert row['error_code'] == 'scenario_knowledge_write_prohibited'
    assert row['raw_source_files']
    assert row['status'] == 'raw_available_summary_protected'
    assert p.progress()['protected'] == 1
    assert p.progress()['failed'] == 0


def test_new_session_cutoff_does_not_enqueue_historical_backlog(tmp_path):
    from lib.context_incremental import ContextIncremental
    old, new = str(uuid.uuid4()), str(uuid.uuid4())
    rollout(tmp_path/'sessions',old,created_at='2026-09-20T01:00:00Z')
    rollout(tmp_path/'sessions',new)
    p = ContextIncremental(tmp_path/'state',tmp_path/'sessions',new_after='2026-10-08T00:00:00Z')
    assert p.discover(now=100)['discovered'] == 1
    assert p.claim(now=200)['session_id'] == new
    assert p.claim(now=200) is None
    assert p.progress()['status'] == 'partial_pending'
