#!/usr/bin/env python3
"""Claude Desktop transcript -> Codex-format rollout, so EP's Scenario Summary pipeline can read desktop chats.  v2 (settle period)

Why: the context/scenario pipeline only understands Codex rollout files (rollout-*-<uuid>.jsonl, first line
`session_meta`, `response_item` messages). It is not changed here; this module emits that exact shape into
~/.evolving-profile/claude-code/rollouts/ (EP's own dir; ~/.codex is never written).

Contract honoured (verified against lib/scenario_source_codec.decode_record):
  * line 0 = session_meta with payload.id == uuid in the filename
  * a `turn_context` row (payload.turn_id: str) opens every turn
  * user text   -> response_item/message role=user      content=[{type:input_text}]  (+ event_msg/user_message like Codex)
  * assistant   -> response_item/message role=assistant content=[{type:output_text}]
        last assistant text of a turn -> phase "final_answer" (visible); earlier ones -> "commentary" (not visible)
  * tool calls/results, thinking, system reminders, sidechains are dropped (same filter as hook_bridge_desktop)

Settle period (v2): a rollout that already exists is rewritten at most once per SETTLE seconds. Rewriting while the
background summariser is working invalidates its job (EP logged >1500 'source revision changed' events for active Codex
sessions). Skipped updates leave a marker in rollouts-pending/ (outside the discovered root); flush_pending() writes them
once the file has been quiet for SETTLE seconds. Nothing is lost: the Claude transcript stays on disk.
Kill switch: create ~/.evolving-profile/claude-code/desktop-rollout.off  (no file is written while it exists).
Never raises into the hook; returns a small status dict for the diagnostic log.
"""
import json, os, re, time, uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path.home() / '.evolving-profile' / 'claude-code'
ROOT = BASE / 'rollouts'
PENDING = BASE / 'rollouts-pending'      # outside ROOT: the pipeline never sees markers
OFF = BASE / 'desktop-rollout.off'
SETTLE = 1200                            # seconds an existing rollout must stay quiet before it is rewritten
MAX_TEXT = 400_000          # chars per message; well under the 8 MiB line ceiling
SKIP_PREFIX = ('<system-reminder>', '<command-', '<local-command', '<ep_', '<evolving_profile',
               '<scheduled-task', '[SCHEDULED TASK - AUTOMATED FIRING')
AUTOMATED_PREFIX = ('<scheduled-task', '[SCHEDULED TASK - AUTOMATED FIRING')


def _text(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_text(x) for x in value]
        return '\n'.join(p for p in parts if p).strip()
    if isinstance(value, dict):
        if value.get('type') in ('tool_use', 'tool_result', 'thinking', 'redacted_thinking', 'image'):
            return ''
        if 'text' in value:
            return str(value.get('text') or '').strip()
        if 'content' in value:
            return _text(value['content'])
    return ''


def _iso(ts, fallback):
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts / (1000 if ts > 1e12 else 1), tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        if isinstance(ts, str) and ts:
            return datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    except Exception:
        pass
    return fallback


def _clip(t):
    return t if len(t) <= MAX_TEXT else t[:MAX_TEXT] + '\n[truncated by desktop_rollout]'


def read_messages(transcript_path):
    """Return [(role, text, iso_ts)] in order from a Claude Code / Cowork JSONL transcript."""
    out = []
    automated_seen = False
    p = Path(transcript_path)
    now = _iso(p.stat().st_mtime, '1970-01-01T00:00:00.000Z')   # deterministic fallback: unchanged transcript -> identical rollout bytes
    for raw in p.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            e = json.loads(raw)
        except Exception:
            continue
        msg = e.get('message') if isinstance(e.get('message'), dict) else None
        role = e.get('role') or (msg or {}).get('role') or e.get('type')
        if role not in ('user', 'assistant') or e.get('isSidechain') or e.get('isMeta'):
            continue
        t = _text((msg or {}).get('content') if msg is not None else e.get('content'))
        if t and t.startswith(AUTOMATED_PREFIX):
            automated_seen = True
        if not t or t.startswith(SKIP_PREFIX):
            continue
        out.append((role, t, _iso(e.get('timestamp'), now)))
    read_messages.automated_seen = automated_seen
    return out


def build_rows(session_id, cwd, messages, host=None):
    first_ts = messages[0][2]
    rows = [{'timestamp': first_ts, 'type': 'session_meta',
             'payload': {'id': session_id, 'timestamp': first_ts, 'cwd': cwd, 'originator': host or 'claude-desktop',
                         'source': host or 'claude-desktop', 'cli_version': 'desktop-bridge-1'}}]
    turns, cur = [], None
    for role, t, ts in messages:
        if role == 'user':
            cur = {'user': (t, ts), 'assistant': []}
            turns.append(cur)
        elif cur is not None:
            cur['assistant'].append((t, ts))
    for n, turn in enumerate(turns, 1):
        ut, uts = turn['user']
        tid = str(uuid.uuid5(uuid.UUID(session_id), f'turn-{n}'))
        rows.append({'timestamp': uts, 'type': 'turn_context', 'payload': {'turn_id': tid, 'cwd': cwd}})
        rows.append({'timestamp': uts, 'type': 'response_item', 'payload': {
            'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': _clip(ut)}]}})
        rows.append({'timestamp': uts, 'type': 'event_msg', 'payload': {'type': 'user_message', 'message': _clip(ut)}})
        last = len(turn['assistant']) - 1
        for i, (at, ats) in enumerate(turn['assistant']):
            rows.append({'timestamp': ats, 'type': 'response_item', 'payload': {
                'type': 'message', 'role': 'assistant', 'phase': 'final_answer' if i == last else 'commentary',
                'content': [{'type': 'output_text', 'text': _clip(at)}]}})
    return rows, len(turns)


def _target(session_id, first_ts):
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    existing = list(ROOT.rglob(f'rollout-*-{session_id}.jsonl'))
    if len(existing) == 1:
        return existing[0]
    if existing:
        raise RuntimeError('ambiguous_existing_rollout')
    d = datetime.strptime(first_ts[:19], '%Y-%m-%dT%H:%M:%S')
    folder = ROOT / f'{d:%Y}' / f'{d:%m}' / f'{d:%d}'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder / f'rollout-{d:%Y-%m-%dT%H-%M-%S}-{session_id}.jsonl'


def _marker(session_id):
    return PENDING / f'{session_id}.json'


def _mark_pending(session_id, transcript_path, cwd, host=None):
    PENDING.mkdir(mode=0o700, parents=True, exist_ok=True)
    m = _marker(session_id)
    tmp = m.with_name(m.name + '.tmp')
    tmp.write_text(json.dumps({'session_id': session_id, 'transcript_path': str(transcript_path), 'cwd': cwd or '', 'host': host or '',
                               'marked_at': time.time()}), encoding='utf-8')
    os.replace(tmp, m)


def _clear_pending(session_id):
    try:
        _marker(session_id).unlink()
    except FileNotFoundError:
        pass


def write_rollout(session_id, transcript_path, cwd, force=False, host=None):
    """Idempotent. A new session is written at once; an existing rollout only after SETTLE quiet seconds (unless force)."""
    try:
        if OFF.exists():
            return {'rollout': 'disabled_by_switch'}
        try:
            session_id = str(uuid.UUID(str(session_id)))
        except ValueError:
            return {'rollout': 'skipped_non_uuid_session'}
        if not transcript_path or not Path(transcript_path).is_file():
            return {'rollout': 'skipped_no_transcript'}
        msgs = read_messages(transcript_path)
        if not any(r == 'user' for r, _, _ in msgs) and getattr(read_messages, 'automated_seen', False):
            return {'rollout': 'skipped_automated_only'}      # scheduled/automated run: nothing a person said, nothing to summarise
        if not any(r == 'user' for r, _, _ in msgs) or not any(r == 'assistant' for r, _, _ in msgs):
            return {'rollout': 'skipped_no_dialogue'}
        # the first record must be a user turn, otherwise leading assistant text has no turn to attach to
        while msgs and msgs[0][0] != 'user':
            msgs.pop(0)
        rows, nturns = build_rows(session_id, cwd or '', msgs, host=host)
        data = ''.join(json.dumps(r, ensure_ascii=False, separators=(',', ':')) + '\n' for r in rows).encode('utf-8')
        path = _target(session_id, rows[0]['timestamp'])
        if path.exists():
            if path.read_bytes() == data:
                _clear_pending(session_id)
                return {'rollout': 'unchanged', 'turns': nturns}
            age = time.time() - path.stat().st_mtime
            if not force and age < SETTLE:
                _mark_pending(session_id, transcript_path, cwd, host=host)
                return {'rollout': 'deferred', 'turns': nturns, 'settle_remaining_s': int(SETTLE - age)}
        tmp = path.with_name(path.name + '.tmp')          # does not match rollout-*.jsonl -> never discovered half-written
        tmp.write_bytes(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        _clear_pending(session_id)
        return {'rollout': 'written', 'turns': nturns, 'bytes': len(data), 'file': path.name}
    except Exception as exc:  # never break the hook
        return {'rollout': f'error:{type(exc).__name__}:{str(exc)[:80]}'}


def flush_pending(max_n=5):
    """Write deferred updates whose rollout has been quiet for SETTLE seconds. Returns how many were flushed."""
    try:
        if OFF.exists() or not PENDING.is_dir():
            return 0
        done = 0
        for m in sorted(PENDING.glob('*.json'))[:max_n * 4]:
            try:
                d = json.loads(m.read_text(encoding='utf-8'))
                sid = str(uuid.UUID(str(d['session_id'])))
            except Exception:
                m.unlink(missing_ok=True)       # unreadable marker: drop it, the next Stop recreates it if still needed
                continue
            existing = list(ROOT.rglob(f'rollout-*-{sid}.jsonl')) if ROOT.is_dir() else []
            if existing and time.time() - existing[0].stat().st_mtime < SETTLE:
                continue                         # still settling
            st = write_rollout(sid, d.get('transcript_path'), d.get('cwd'), force=True, host=d.get('host') or None)
            if st.get('rollout') in ('written', 'unchanged'):
                done += 1
            if st.get('rollout') in ('written', 'unchanged') or str(st.get('rollout', '')).startswith('skipped'):
                m.unlink(missing_ok=True)
            if done >= max_n:
                break
        return done
    except Exception:
        return 0
