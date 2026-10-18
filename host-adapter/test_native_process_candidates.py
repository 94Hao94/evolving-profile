import json

from lib.process_memory import ProcessMemoryStore
from lib import process_context


def rollout(tmp_path, *, success=True, repair=True, duplicate=False):
    rows = [ {'type': 'session_meta', 'payload': {'id': 'native-session'}},
        {'type': 'turn_context', 'payload': {'turn_id': 'native-turn', 'cwd': '/task',
                                           'model': 'observed-model', 'model_provider': 'observed-provider'}}]
    def invocation(call, name, args, output):
        rows.append({'type': 'response_item', 'payload': {'type': 'function_call',
            'name': name, 'arguments': json.dumps(args), 'call_id': call}})
        rows.append({'type': 'response_item', 'payload': {'type': 'function_call_output',
            'call_id': call, 'output': json.dumps(output)}})
    invocation('failed', 'exec_command', {'cmd': 'python -m pytest tests/test_rows.py', 'workdir': '/task'},
               {'exit_code': 1, 'output': 'FAILED test_rows: private output must not be copied'})
    if repair:
        invocation('repair', 'apply_patch', {'patch': 'sensitive source body'}, {'success': True})
    if success:
        invocation('passed', 'exec_command', {'cmd': 'python -m pytest tests/test_rows.py', 'workdir': '/task'},
                   {'exit_code': 0, 'output': '1 passed'})
    rows.append({'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant',
        'phase': 'final_answer', 'content': [{'type': 'output_text', 'text': 'Fully verified; reusable strategy'}]}})
    if duplicate:
        rows.extend(rows[2:4])
    path = tmp_path / 'native.jsonl'
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return path


def capture(path, store, **extra):
    return process_context.capture_native_process(path, store, session_id='native-session',
        bank_id='bank-a', project='/task', allowed_turn_ids={'native-turn'}, **extra)


def test_native_failure_patch_same_test_pass_yields_only_source_bound_candidate(tmp_path):
    path = rollout(tmp_path)
    store = ProcessMemoryStore(tmp_path / 'records.json')
    capture(path, store)
    rows = store.all()
    assert len([r for r in rows if r['kind'] == 'trace']) == 3
    candidate = next(r for r in rows if r['kind'] == 'process_draft')
    assert candidate['status'] == 'candidate'
    assert candidate['task_verified'] is False
    assert candidate['outcome'] == 'ambiguous'
    assert candidate['primary_context']['session_id'] == 'native-session'
    assert candidate['model_profile']['family'] == 'observed-model'
    assert len(candidate['source_trace_ids']) == 3
    assert len(candidate['native_evidence_locators']) == 6
    assert not any(r['kind'] in {'episode', 'pattern', 'skill'} for r in rows)
    assert 'sensitive source' not in json.dumps(rows)
    assert 'private output' not in json.dumps(rows)
    before = store.path.read_bytes()
    capture(path, store)
    assert store.path.read_bytes() == before


def test_assistant_claim_and_single_tool_receipt_do_not_make_repair_candidate(tmp_path):
    for repair, success in [(False, True), (True, False), (False, False)]:
        path = rollout(tmp_path, repair=repair, success=success)
        store = ProcessMemoryStore(tmp_path / f'records-{repair}-{success}.json')
        capture(path, store)
        assert not any(r['kind'] == 'process_draft' for r in store.all())


def test_replayed_output_or_wrong_task_cannot_manufacture_candidate(tmp_path):
    path = rollout(tmp_path, repair=False, duplicate=True)
    store = ProcessMemoryStore(tmp_path / 'records.json')
    capture(path, store)
    assert not any(r['kind'] == 'process_draft' for r in store.all())
    blocked = ProcessMemoryStore(tmp_path / 'blocked.json')
    process_context.capture_native_process(path, blocked, session_id='native-session', bank_id='bank-a',
        project='/task', allowed_turn_ids=set())
    assert not blocked.all()


def test_native_context_metadata_mismatch_is_held(tmp_path):
    path = rollout(tmp_path)
    store = ProcessMemoryStore(tmp_path / 'records.json')
    result = process_context.capture_native_process(path, store, session_id='another-session',
        bank_id='bank-a', project='/task', allowed_turn_ids={'native-turn'})
    assert result['reason'] == 'native_session_mismatch'
    assert not store.all()


def test_stop_capture_respects_runtime_modules_and_write_prohibitions(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    # MCP tests may put the live Hook directory first in sys.path. Load the
    # exact development entrypoint so this test cannot silently exercise it.
    spec = importlib.util.spec_from_file_location('native_process_retain_under_test', Path(__file__).with_name('retain.py'))
    retain = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(retain)
    path = rollout(tmp_path)
    monkeypatch.setenv('EVOLVING_PROFILE_STATE_ROOT', str(tmp_path))
    config = {'processMemoryPath': str(tmp_path / 'records.json')}
    hook = {'transcript_path': str(path), 'session_id': 'native-session', 'cwd': '/task'}
    turn = {'write_policy': {'knowledge_allowed': True}, 'messages': [
        {'role': 'user', 'source_record': {'turn_id': 'native-turn'}}]}
    settings = tmp_path / 'config/runtime-settings.json'
    settings.parent.mkdir()
    settings.write_text(json.dumps({'modules': {'agent_process_memory': {'record': False}}}))
    retain.capture_native_process_on_stop(hook, config, 'bank-a', [turn])
    assert not (tmp_path / 'records.json').exists()
    settings.write_text('{}')
    denied = {**turn, 'write_policy': {'knowledge_allowed': False}}
    retain.capture_native_process_on_stop(hook, config, 'bank-a', [turn, denied])
    assert not (tmp_path / 'records.json').exists()
    retain.capture_native_process_on_stop(hook, config, 'bank-a', [turn])
    assert any(r['kind'] == 'process_draft' for r in ProcessMemoryStore(config['processMemoryPath']).all())


def test_real_codemode_array_outputs_keep_metadata_without_trusting_stdout(tmp_path):
    path = rollout(tmp_path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        payload = row['payload']
        if payload.get('type') == 'function_call':
            args = json.loads(payload.pop('arguments'))
            if payload['name'] == 'exec_command':
                payload.update(type='custom_tool_call', name='exec', input='text(await tools.exec_command(' + json.dumps(args) + '));')
        if payload.get('type') == 'function_call_output':
            payload.update(type='custom_tool_call_output', output=[
                {'type': 'input_text', 'text': 'Script completed\nWall time 0.1 seconds\nOutput:\n'},
                {'type': 'input_text', 'text': payload['output']}])
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    store = ProcessMemoryStore(tmp_path / 'records.json')
    capture(path, store)
    assert len([r for r in store.all() if r['kind'] == 'process_draft']) == 1
    # The actual audited source often prints r.output only. No exit-code
    # receipt survives that projection; an assistant-style 'passed' is not one.
    for row in rows:
        payload = row['payload']
        if payload.get('type') == 'custom_tool_call_output':
            payload['output'][1]['text'] = 'All tests passed; fully verified.'
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    unverified = ProcessMemoryStore(tmp_path / 'unverified.json')
    capture(path, unverified)
    assert not any(r['kind'] == 'process_draft' for r in unverified.all())
    assert all(r['tool_success'] is None for r in unverified.all())


def test_codemode_constant_json_cannot_impersonate_inner_exit_receipts(tmp_path):
    path = rollout(tmp_path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        payload = row['payload']
        if payload.get('type') == 'function_call' and payload.get('name') == 'exec_command':
            args = json.loads(payload.pop('arguments'))
            code = 1 if payload['call_id'] == 'failed' else 0
            payload.update(type='custom_tool_call', name='exec',
                input='await tools.exec_command(' + json.dumps(args) + '); text({"exit_code":' + str(code) + '});')
        if payload.get('type') == 'function_call_output' and payload.get('call_id') in {'failed', 'passed'}:
            payload.update(type='custom_tool_call_output', output=[
                {'type': 'input_text', 'text': json.dumps({'exit_code': 1 if payload['call_id'] == 'failed' else 0})}])
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    store = ProcessMemoryStore(tmp_path / 'records.json')
    capture(path, store)
    assert not any(r['kind'] == 'process_draft' for r in store.all())
    assert all(r['tool_success'] is None for r in store.all() if r.get('toolchain') != ['apply_patch'])
