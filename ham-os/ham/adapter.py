from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import digest
from .storage import IdempotencyConflict

_TOOL_RESPONSE_ARCHIVE_SCHEMA = 'ham.tool-response-archive.v1'
_TOOL_RESPONSE_ARCHIVE_THRESHOLD_BYTES = 32 * 1024


def _now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def flags(path=Path.home() / '.hindsight/memory-contract-v5.json'):
    try:
        return json.loads(path.read_text()).get('memoryOS') or {}
    except Exception:
        return {}


def _id(value):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))))


def _capture_root():
    return Path(os.environ.get('HAM_CAPTURE_STATE_DIR') or Path.home() / '.hindsight/memory-os/capture')


@contextmanager
def _capture_db():
    root = _capture_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(root / 'capture.sqlite3', timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('''CREATE TABLE IF NOT EXISTS captures(
            capture_order INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_key TEXT UNIQUE NOT NULL, input_hash TEXT NOT NULL,
            envelope_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at REAL NOT NULL DEFAULT 0,
            last_error TEXT)''')
        yield conn
    finally:
        conn.close()


def _canonical_tool_response(response):
    if isinstance(response, str):
        return 'text', response.encode('utf-8')
    return 'json', json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _archive_tool_response(response, root, *, force=False):
    """Store a large host tool response once and return an immutable receipt."""
    response_kind, payload = _canonical_tool_response(response)
    threshold = max(1, int(os.environ.get('HAM_TOOL_RESPONSE_ARCHIVE_THRESHOLD_BYTES', _TOOL_RESPONSE_ARCHIVE_THRESHOLD_BYTES)))
    if not force and len(payload) < threshold:
        return None
    digest = hashlib.sha256(payload).hexdigest()
    relative = Path('tool-response-archive') / 'objects' / digest[:2] / f'{digest}.bin'
    target = Path(root) / relative
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.exists():
        if target.read_bytes() != payload:
            raise ValueError('tool_response_archive_hash_collision')
    else:
        temporary = target.with_suffix('.tmp')
        temporary.write_bytes(payload)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise ValueError('tool_response_archive_hash_mismatch')
    return {
        'schema': _TOOL_RESPONSE_ARCHIVE_SCHEMA,
        'sha256': digest,
        'bytes': len(payload),
        'kind': response_kind,
        'object_path': relative.as_posix(),
    }


def read_archived_tool_response(source, root=None):
    """Read a hash-verified large tool response referenced by a capture envelope."""
    receipt = (source or {}).get('tool_response_archive') if isinstance(source, dict) else None
    if not isinstance(receipt, dict):
        return None
    digest = str(receipt.get('sha256') or '')
    expected = Path('tool-response-archive') / 'objects' / digest[:2] / f'{digest}.bin'
    if receipt.get('schema') != _TOOL_RESPONSE_ARCHIVE_SCHEMA or Path(str(receipt.get('object_path') or '')) != expected:
        raise ValueError('tool_response_archive_invalid_receipt')
    payload = (Path(root) if root is not None else _capture_root()) / expected
    raw = payload.read_bytes()
    if len(raw) != int(receipt.get('bytes') or -1) or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('tool_response_archive_hash_mismatch')
    if receipt.get('kind') == 'text':
        return raw.decode('utf-8')
    if receipt.get('kind') == 'json':
        return json.loads(raw)
    raise ValueError('tool_response_archive_unknown_kind')


def _source_identity(hook_name, source, occurrence_id=None):
    for key in ('hook_invocation_id', 'invocation_id', 'event_id'):
        if source.get(key) is not None and str(source[key]):
            return {key: source[key]}, key
    if hook_name == 'UserPromptSubmit':
        for key in ('message_id', 'user_message_id'):
            if source.get(key):
                return {key: source[key]}, key
        if occurrence_id:
            return {'local_hook_invocation': str(occurrence_id)}, 'local_hook_invocation'
        # Steering messages share a turn; even identical text may be a new input.
        return {'capture_id': str(uuid.uuid4())}, 'unavailable'
    turn = source.get('turn_id')
    tool = source.get('tool_use_id') or source.get('tool_call_id')
    if tool:
        return {'turn_id': turn, 'tool_id': tool}, 'tool_occurrence'
    # A turn cannot identify several uses of the same tool in that turn.
    if turn and not (source.get('tool_name') or 'Tool' in hook_name):
        return {'turn_id': turn}, 'turn_occurrence'
    return {'capture_id': str(uuid.uuid4())}, 'unavailable'


def event_from_hook(hook_name: str, hook_input: dict[str, Any], origin_class='ambient_context', event_type='turn', body_preview='', *, occurrence_id=None):
    """Durably capture first; an identified retry returns the original envelope.

    Without host occurrence identity each call is new: text is never identity.
    Full supplied input is retained, but no transcript is fabricated.
    """
    source = json.loads(json.dumps(hook_input, ensure_ascii=False))
    archived_tool_response = None
    if hook_name == 'PostToolUse' and source.get('tool_response') is not None:
        try:
            archived_tool_response = _archive_tool_response(source['tool_response'], _capture_root())
        except Exception:
            # The legacy full envelope is the evidence-preserving fallback.
            archived_tool_response = None
        if archived_tool_response is not None:
            source.pop('tool_response', None)
            source['tool_response_archive'] = archived_tool_response
    session = str(source.get('session_id') or 'unknown')
    project = str(source.get('cwd') or 'unknown')
    identity, basis = _source_identity(hook_name, source, occurrence_id)
    key_data = {'adapter': 'codex', 'session': session, 'project': project, 'hook': hook_name, 'identity': identity}
    key = digest(key_data)
    input_hash = digest({'hook': hook_name, 'source': source, 'origin_class': origin_class, 'event_type': event_type, 'body': body_preview})
    with _capture_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        try:
            row = conn.execute('SELECT input_hash,envelope_json FROM captures WHERE identity_key=?', (key,)).fetchone()
            if row:
                if row['input_hash'] != input_hash:
                    raise IdempotencyConflict('capture_idempotency_conflict')
                conn.commit()
                return json.loads(row['envelope_json'])
            now = _now()
            source_time = source.get('occurred_at') or source.get('timestamp')
            if hook_name == 'Stop':
                body = source.get('last_assistant_message') or body_preview or ''
            elif hook_name == 'PostToolUse' and hook_input.get('tool_response') is not None:
                response_body = hook_input['tool_response']
                body = response_body if isinstance(response_body, str) else json.dumps(response_body, ensure_ascii=False)
            elif hook_name == 'UserPromptSubmit':
                body = body_preview or source.get('prompt') or source.get('user_prompt') or ''
            else:
                body = body_preview or ''
            source_sequence = source.get('source_sequence', source.get('sequence'))
            if type(source_sequence) is not int or source_sequence < 0:
                source_sequence = None
            order = conn.execute('INSERT INTO captures(identity_key,input_hash,envelope_json) VALUES(?,?,?)', (key, input_hash, '{}')).lastrowid
            payload = {
                'schema': 'ham.event.v1', 'event_id': _id(key_data), 'idempotency_key': key,
                'principal_id': 'liuzhongyang', 'agent_id': 'codex', 'session_id': session,
                'project_id': hashlib.sha256(project.encode()).hexdigest()[:24],
                'task_id': hashlib.sha256((session + '|' + project).encode()).hexdigest()[:24],
                'sequence': source_sequence if source_sequence is not None else order,
                'sequence_basis': 'source' if source_sequence is not None else 'local_capture',
                'source_sequence': source_sequence, 'origin_class': origin_class, 'event_type': event_type,
                'occurred_at': source_time or now, 'recorded_at': now,
                'body_ref': archived_tool_response or source.get('body_ref'), 'body_preview': body[:4096],
                'body_text': body[:4096] if archived_tool_response is not None else body,
                'source_uri': source.get('source_uri'), 'source_payload': source,
                'parent_event_ids': source.get('parent_event_ids') or [],
                'injected_memory_ids': source.get('injected_memory_ids') or [],
                'visibility_scope': source.get('visibility_scope') or 'principal_shared', 'status': 'persisted',
                'provenance': {'hook': hook_name, 'retry_identity': basis,
                    'hook_invocation_id': str(occurrence_id) if occurrence_id else source.get('hook_invocation_id'),
                    'occurred_at_basis': 'source' if source_time else 'local_capture',
                    'body_evidence': ('archived_supplied_tool_response' if archived_tool_response is not None
                                      else 'supplied_text' if body else 'missing'),
                    'transcript_evidence': 'reference_unverified' if source.get('transcript_path') else 'missing'},
            }
            conn.execute('UPDATE captures SET envelope_json=? WHERE capture_order=?', (json.dumps(payload, ensure_ascii=False, sort_keys=True), order))
            conn.commit()
            return payload
        except BaseException:
            conn.rollback()
            raise


def retry_pending(limit=10, *, force=False):
    """Attempt at most 10 saved envelopes, once each; no background worker.

    After restart or a lost remote receipt the original envelope is replayed.
    Concurrent drains may deliver twice; remote idempotency makes this safe.
    """
    with _capture_db() as conn:
        rows = conn.execute("SELECT * FROM captures WHERE status='pending' AND (? OR next_attempt_at<=?) ORDER BY capture_order LIMIT ?", (force, time.time(), max(0, min(10, int(limit))))).fetchall()
        outcomes = []
        for row in rows:
            payload = json.loads(row['envelope_json'])
            result = {'attempted': True, 'capture_durable': True, 'event_id': payload['event_id']}
            req = urllib.request.Request('http://127.0.0.1:8879/v2/memory-os/events', data=row['envelope_json'].encode(), headers={'Content-Type': 'application/json', 'Idempotency-Key': payload['idempotency_key'], 'X-HAM-Adapter': 'codex'}, method='POST')
            try:
                with urllib.request.urlopen(req, timeout=0.75) as response:
                    receipt = json.load(response)
                    result.update(http=response.status, receipt=receipt)
                    if response.status != 200 or receipt.get('durable') is not True:
                        raise ValueError('missing_durable_receipt')
                conn.execute("UPDATE captures SET status='delivered',attempts=attempts+1,last_error=NULL WHERE capture_order=?", (row['capture_order'],))
            except Exception as exc:
                result['error'] = f'{type(exc).__name__}:{exc}'
                permanent = isinstance(exc, urllib.error.HTTPError) and exc.code in (400, 401, 403, 409, 413, 422)
                result['delivery_status'] = 'blocked' if permanent else 'pending'
                conn.execute("UPDATE captures SET status=?,attempts=attempts+1,next_attempt_at=?,last_error=? WHERE capture_order=? AND status='pending'", (result['delivery_status'], time.time() + min(300, 2 ** min(row['attempts'], 8)), result['error'], row['capture_order']))
            outcomes.append(result)
        return outcomes


def emit(hook_name, hook_input, origin_class='ambient_context', event_type='turn', body_preview='', *, occurrence_id=None):
    f = flags()
    if not (f.get('enabled') and f.get('ledgerDualWrite')):
        return {'attempted': False, 'reason': 'flag_disabled'}
    try:
        payload = event_from_hook(hook_name, hook_input, origin_class, event_type, body_preview, occurrence_id=occurrence_id)
    except Exception as exc:
        return {'attempted': False, 'capture_durable': False, 'error': f'{type(exc).__name__}:{exc}'}
    results = retry_pending(limit=2)
    return next((r for r in results if r['event_id'] == payload['event_id']),
                {'attempted': False, 'capture_durable': True, 'event_id': payload['event_id'], 'reason': 'captured_no_attempt_due'})
