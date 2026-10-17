"""Read bounded native Session metadata for an already verified Prompt binding."""
import hashlib
import json
import uuid
import re
from pathlib import Path


def resolve_source_metadata(binding, session_root, *, tail_bytes=262144):
    if binding.get('state') != 'prompt_bound' or not binding.get('turn_id'): return {}
    try: sid = str(uuid.UUID(str(binding.get('session_id'))))
    except (ValueError, TypeError): return {}
    root = Path(session_root).expanduser()
    paths = list(root.rglob(f'rollout-*-{sid}.jsonl'))[:8] if root.is_dir() else []
    matched = []
    for path in paths:
        try:
            with path.open('rb') as stream:
                stream.seek(0, 2); size = stream.tell()
                start = max(0, size-tail_bytes); stream.seek(start)
                if start: stream.readline()
                while True:
                    offset = stream.tell(); raw = stream.readline()
                    if not raw or not raw.endswith(b'\n'): break
                    try: row = json.loads(raw)
                    except (ValueError, UnicodeError): continue
                    payload = row.get('payload') or {}
                    if row.get('type') == 'turn_context' and str(payload.get('turn_id') or '') == str(binding['turn_id']):
                        matched.append({**{k: payload[k] for k in ('cwd','model','model_provider') if payload.get(k)},
                            'transcript_path': str(path), 'raw_context_locator': {'source_path': str(path),
                            'byte_offset': offset, 'raw_line_sha256': hashlib.sha256(raw).hexdigest()}})
        except (OSError, TypeError): continue
    if len(matched) != 1: return {}
    return matched[0]


def _native_call(payload):
    name = str(payload.get('name') or '')
    short = name.rsplit('.', 1)[-1]
    raw = payload.get('arguments', payload.get('input', ''))
    try:
        args = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        args = {}
    args = args if isinstance(args, dict) else {}
    command = str(args.get('cmd') or '')
    workdir = str(args.get('workdir') or '')
    # functions.exec is a transport wrapper. Decode only one literal command;
    # never execute JavaScript or infer a command from arbitrary narrative.
    if short == 'exec' and isinstance(raw, str):
        matches = re.findall(r'tools\.exec_command\(\{\s*"?cmd"?\s*:\s*("(?:[^"\\]|\\.)*")', raw)
        if len(matches) == 1 and raw.count('tools.exec_command(') == 1:
            try: command = json.loads(matches[0]); short = 'exec_command'
            except ValueError: pass
            directory = re.search(r'"?workdir"?\s*:\s*("(?:[^"\\]|\\.)*")', raw)
            if directory:
                try: workdir = json.loads(directory[1])
                except ValueError: pass
    return short, command, workdir


def _exact_exec_result_projection(payload):
    """A tiny literal grammar, not JavaScript execution or data-flow guessing."""
    raw = payload.get('arguments', payload.get('input', ''))
    if not isinstance(raw, str): return False
    direct = re.fullmatch(r'\s*text\(\s*await\s+tools\.exec_command\((\{.*\})\)\s*\)\s*;?\s*', raw, re.S)
    assigned = re.fullmatch(r'\s*(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*await\s+tools\.exec_command\((\{.*\})\)\s*;\s*text\(\s*\1\s*\)\s*;?\s*', raw, re.S)
    args = direct[1] if direct else assigned[2] if assigned else None
    if args is None: return False
    # Permit literal unquoted property names used by the native code tool.
    # JSON decoding then rejects expressions, extra statements and mutations.
    args = re.sub(r'([{,]\s*)([A-Za-z_][\w]*)\s*:', r'\1"\2":', args)
    try: value = json.loads(args)
    except ValueError: return False
    return isinstance(value, dict) and isinstance(value.get('cmd'), str)


def _native_result(payload):
    value = payload.get('output')
    if isinstance(value, list):
        receipts = []
        for block in value:
            if not isinstance(block, dict) or block.get('type') not in {'input_text', 'text'}: continue
            try: decoded = json.loads(block.get('text') or '')
            except (ValueError, TypeError): continue
            if isinstance(decoded, dict) and (type(decoded.get('exit_code')) is int or type(decoded.get('success')) is bool):
                receipts.append(decoded)
        # Multiple tool results from one code cell cannot be attributed to an
        # individual nested command without a native subcall identity.
        return receipts[0] if len(receipts) == 1 else {}
    if isinstance(value, str):
        try: value = json.loads(value)
        except ValueError: return {}
    return value if isinstance(value, dict) else {}


def capture_native_process(transcript_path, store, *, session_id, bank_id, project,
                           allowed_turn_ids, max_bytes=4 * 1024 * 1024):
    """Capture source-bound attempts and conservative repair hypotheses locally.

    A successful test receipt is evidence of that command only. It does not
    verify the requested task, the patch's causal role, or a reusable strategy.
    No prompt, source patch, command arguments or output bodies are retained.
    """
    allowed = {str(turn) for turn in allowed_turn_ids if turn}
    if not allowed or not bank_id or not session_id:
        return {'traces': 0, 'candidates': 0, 'reason': 'authorized_source_turn_required'}
    path = Path(transcript_path).expanduser().resolve()
    calls, completed, turn, native_session, metadata = {}, [], None, None, {}
    with path.open('rb') as stream:
        # Verify the original Session header even when scanning a bounded tail.
        first = stream.readline()
        try:
            header = json.loads(first)
            if header.get('type') == 'session_meta':
                native_session = (header.get('payload') or {}).get('id')
        except (ValueError, UnicodeError): pass
        if native_session != session_id:
            return {'traces': 0, 'candidates': 0, 'reason': 'native_session_mismatch'}
        size = stream.seek(0, 2); start = max(0, size - max_bytes)
        stream.seek(start)
        if start: stream.readline()
        while True:
            offset = stream.tell(); raw = stream.readline()
            if not raw or not raw.endswith(b'\n'): break
            try: row = json.loads(raw)
            except (ValueError, UnicodeError): continue
            payload = row.get('payload') or {}
            if not isinstance(payload, dict): continue
            if row.get('type') == 'turn_context':
                turn = str(payload.get('turn_id') or '')
                metadata = {key: payload.get(key) for key in ('cwd', 'model', 'model_provider')}
                continue
            if turn not in allowed: continue
            digest = hashlib.sha256(raw).hexdigest()
            locator = {'source_path': str(path), 'byte_offset': offset, 'raw_line_sha256': digest}
            kind = payload.get('type')
            call_id = str(payload.get('call_id') or '')
            if not call_id: continue
            if row.get('type') == 'response_item' and kind in {'function_call', 'custom_tool_call'}:
                name, command, workdir = _native_call(payload)
                if not name or name.startswith(('record_agent_', 'promote_agent_')): continue
                # A replayed call ID never becomes another independent event.
                calls.setdefault(call_id, {'name': name, 'command': command, 'workdir': workdir,
                    'locator': locator, 'turn_id': turn, 'metadata': dict(metadata),
                    'timestamp': row.get('timestamp'), 'id': 'trace:raw:' + digest,
                    'result_projection_bound': str(payload.get('name') or '').rsplit('.', 1)[-1] != 'exec' or _exact_exec_result_projection(payload)})
                continue
            call = calls.get(call_id)
            if not call or call['turn_id'] != turn or call.get('completed'): continue
            result = {}
            if row.get('type') == 'response_item' and kind in {'function_call_output', 'custom_tool_call_output'}:
                result = _native_result(payload) if call['result_projection_bound'] else {}
            elif row.get('type') == 'event_msg' and kind in {'exec_command_end', 'patch_apply_end'}:
                result = payload
            else: continue
            code = result.get('exit_code')
            succeeded = code == 0 if type(code) is int else result.get('success')
            if succeeded is not True and succeeded is not False: succeeded = None
            call.update(completed=True, result_locator=locator, tool_success=succeeded, result_code=code)
            completed.append(call)
    # Invocation without an output remains observed, never assumed successful.
    added = 0; candidates = 0
    with store.locked():
        known = {row.get('process_memory_id') for row in store.all()}
        for call in calls.values():
            if call['id'] in known: continue
            model = call['metadata']
            store.record_trajectory({'process_memory_id': call['id'], 'bank_id': bank_id,
                'text': 'Native tool invocation: ' + call['name'], 'outcome': 'ambiguous',
                'phase': 'act', 'process_dimensions': ['tool_use'], 'toolchain': [call['name']],
                'tool_returned': bool(call.get('completed')), 'tool_success': call.get('tool_success'),
                'raw_source_locator': call['locator'], 'tool_result_locator': call.get('result_locator'),
                'primary_context': {'session_id': session_id, 'turn_id': call['turn_id'], 'cwd': project, 'bank_id': bank_id},
                'model_profile': {'family': model.get('model') or 'unknown', 'version': 'observed_runtime_version_unknown'},
                'environment_fingerprint': {'host': 'codex_native_rollout', 'cwd': model.get('cwd'),
                    'model_provider': model.get('model_provider'), 'toolchain': [call['name']]},
                'verification_evidence': [], 'evidence_role': 'native_tool_receipt_not_task_verification',
                **({'created_at': call['timestamp']} if call['timestamp'] else {})})
            known.add(call['id']); added += 1
        failures, repairs = {}, {}
        for call in completed:
            turn = call['turn_id']
            if call['name'] == 'apply_patch' and call.get('tool_success') is True:
                repairs[turn] = call
                continue
            command = call['command']
            if call['name'] != 'exec_command' or not re.search(r'\b(?:pytest|npm\s+(?:run\s+)?test|pnpm\s+test|cargo\s+test|go\s+test)\b', command): continue
            key = (turn, command, call['workdir'])
            if call.get('tool_success') is False:
                failures[key] = call
                repairs.pop(turn, None)
                continue
            failed, repair = failures.get(key), repairs.get(turn)
            if call.get('tool_success') is not True or not failed or not repair: continue
            sources = [failed, repair, call]
            identity = 'candidate:native-repair:' + hashlib.sha256('|'.join(c['id'] for c in sources).encode()).hexdigest()
            if any(row.get('native_candidate_id') == identity for row in store.all()): continue
            store.record_process_draft({'text': 'Task-local candidate: a failing native test, successful patch receipt and identical test rerun were observed. Causality and task completion remain unverified.',
                'status': 'candidate', 'bank_id': bank_id, 'outcome': 'ambiguous',
                'failure_signature': ['native_test_nonzero_exit'], 'repair_actions': ['native_patch_receipt_between_test_runs'],
                'source_trace_ids': [c['id'] for c in sources], 'native_candidate_id': identity,
                'native_evidence_locators': [loc for c in sources for loc in (c['locator'], c['result_locator'])],
                'primary_context': {'session_id': session_id, 'turn_id': turn, 'cwd': project, 'bank_id': bank_id},
                'model_profile': {'family': call['metadata'].get('model') or 'unknown', 'version': 'observed_runtime_version_unknown'},
                'environment_fingerprint': {'host': 'codex_native_rollout', 'cwd': call['metadata'].get('cwd'),
                    'model_provider': call['metadata'].get('model_provider'), 'toolchain': ['exec_command', 'apply_patch']},
                'transfer_scope': {'transfer_status': 'candidate', 'session_ids': [session_id]},
                'rollout_state': 'shadow', 'verification_evidence': [], 'candidate_reason': 'source_bound_sequence_requires_independent_task_verification'})
            candidates += 1
    return {'traces': added, 'candidates': candidates, 'reason': 'native_evidence_only'}
