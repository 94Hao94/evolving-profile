import json

from lib.process_memory import ProcessMemoryStore


def test_unverified_legacy_success_is_exposed_as_ambiguous_without_rewriting_source(tmp_path):
    path = tmp_path / 'records.json'
    path.write_text(json.dumps({'records': [{'process_memory_id': 'old', 'kind': 'trace',
        'maturity': 'observed', 'outcome': 'correct', 'source_trace_ids': ['old'],
        'tool_result': {'status': 'returned', 'returned_count': 0}}]}))
    before = path.read_bytes()
    row = ProcessMemoryStore(path).all()[0]
    assert row['outcome'] == 'ambiguous'
    assert row['recorded_outcome'] == 'correct'
    assert row['task_verified'] is False
    assert path.read_bytes() == before


def test_mechanical_receipt_cannot_verify_or_promote_task(tmp_path):
    store = ProcessMemoryStore(tmp_path / 'records.json')
    row = store.record_trajectory({'text': 'Research returned zero', 'outcome': 'correct',
        'verification_evidence': [{'verifier_kind': 'deterministic_tool', 'status': 'passed',
                                   'scope': 'tool_execution_only'}]})
    assert row['outcome'] == 'ambiguous'
    assert row['task_verified'] is False
    assert store.auto_promote_verified_process() == {'episodes': 0, 'patterns': 0}


def test_task_verifier_preserves_actual_task_outcome(tmp_path):
    row = ProcessMemoryStore(tmp_path / 'records.json').record_trajectory({
        'text': 'test repair', 'outcome': 'recovered',
        'verification_evidence': [{'verifier_kind': 'automated_test', 'status': 'passed',
                                   'scope': 'task_result'}]})
    assert row['outcome'] == 'recovered'
    assert row['task_verified'] is True


def test_mcp_empty_research_is_successful_tool_return_not_task_success(tmp_path, monkeypatch):
    import evolving_profile_controller_mcp as mcp
    monkeypatch.setattr(mcp, 'PROCESS_MEMORY_PATH', tmp_path / 'records.json')
    monkeypatch.setattr(mcp, 'runtime_disabled', lambda *_: None)
    mcp.capture_tool_trajectory('user_research', {}, outcome='correct',
        result={'status': 'complete', 'memories': []}, tool_call_id='native-call')
    row = ProcessMemoryStore(tmp_path / 'records.json').all()[0]
    assert row['outcome'] == 'ambiguous'
    assert row['tool_success'] is True
    assert row['tool_returned'] is True
    assert row['task_verified'] is False
    assert row['tool_result']['returned_count'] == 0
