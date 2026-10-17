"""Incremental raw-message locators; no model calls or memory publication.

Uses a private sidecar, never changes the capture queue or scenario index.
Raw line hashes are rechecked at readback. Assistant claims stay claims.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path
from .content import extract_user_request, is_synthetic_codex_user_message
from .session_paths import session_paths


def _decode_record(raw):
    """Validate evidence-bearing records; unknown event kinds stay ignorable."""
    try:
        row = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('invalid_json') from None
    if not isinstance(row, dict):
        raise ValueError('invalid_record_shape')
    if row.get('type') not in ('turn_context', 'response_item'):
        return row, {}, None
    payload = row.get('payload')
    if not isinstance(payload, dict):
        raise ValueError('invalid_record_payload')
    if row.get('type') == 'turn_context':
        if payload.get('turn_id') is not None and not isinstance(payload['turn_id'], str):
            raise ValueError('invalid_turn_id')
        return row, payload, None
    if payload.get('type') != 'message':
        return row, payload, None
    role, phase = payload.get('role'), payload.get('phase')
    if not isinstance(role, str):
        raise ValueError('invalid_message_role')
    if phase is not None and not isinstance(phase, str):
        raise ValueError('invalid_message_phase')
    content = payload.get('content', [])
    if (not isinstance(content, list) or any(not isinstance(item, dict) or
            ('text' in item and not isinstance(item['text'], str)) for item in content)):
        raise ValueError('invalid_message_content')
    if row.get('timestamp') is not None and not isinstance(row['timestamp'], str):
        raise ValueError('invalid_message_timestamp')
    text = '\n'.join(item.get('text', '') for item in content)
    eligible = role == 'user' or (role == 'assistant' and phase in {'final', 'final_answer'})
    meaningful = role == 'assistant' or (bool(extract_user_request(text)) and
        not is_synthetic_codex_user_message(text) and not text.lstrip().startswith('<heartbeat>'))
    return row, payload, text if eligible and meaningful and text.strip() else None


def read_evidence(session_id, root, *, turn_id=None, max_chars=12000, cache_root=None,
                  max_scan_bytes=16*1024*1024, max_line_bytes=1024*1024,coverage_root=None,raw_line_sha256=None):
    for value in (max_chars, max_scan_bytes, max_line_bytes):
        if type(value) is not int or value < 1:
            raise ValueError('raw_evidence_budgets_must_be_positive_integers')
    sid = str(uuid.UUID(str(session_id)))
    if raw_line_sha256 is not None and not re.fullmatch('[0-9a-f]{64}',raw_line_sha256):raise ValueError('raw_record_hash_invalid')
    root = Path(root).expanduser()
    cache = Path(cache_root or Path.home() / ".evolving-profile/audit/raw-session-locators")
    located = session_paths(root,sid)
    if coverage_root and raw_line_sha256:
        from .scenario_raw_readback import read_materialized
        prepared=read_materialized(sid,root,coverage_root,turn_id=turn_id,max_chars=max_chars,
            max_line_bytes=max_line_bytes,raw_line_sha256=raw_line_sha256)
        if prepared is not None:return prepared
    paths = located['paths']
    base = {"source_type": "codex_thread_history", "claims_independently_verified": False,
            "boundary": "original_message_readback_not_artifact_or_external_fact_verification"}
    if located['status'] != 'ready':
        if located['status']=='source_compressed_unavailable':
            from .scenario_raw_readback import read_compressed
            result=read_compressed(sid,root,turn_id=turn_id,max_chars=max_chars,max_scan_bytes=max_scan_bytes,
                max_line_bytes=max_line_bytes,coverage_root=coverage_root,raw_line_sha256=raw_line_sha256)
            if result is not None:return {**base,**result}
        return {**base, "status": located['status'], "source": {},
                "coverage": {"matched_messages": None, **located.get('coverage', {})}}
    cache.mkdir(parents=True, exist_ok=True)
    cache.chmod(0o700)
    cache_db = cache / (sid + '.sqlite')
    cache_db.touch(exist_ok=True)
    cache_db.chmod(0o600)
    with (cache / (sid + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with sqlite3.connect(cache_db, timeout=10) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS checkpoint(path TEXT PRIMARY KEY, offset INTEGER, turn_id TEXT, inode INTEGER);
                CREATE TABLE IF NOT EXISTS message(path TEXT, offset INTEGER, hash TEXT, role TEXT, turn_id TEXT, text TEXT, at TEXT, PRIMARY KEY(path,offset));
            """)
            scanned_bytes, scanned_records, scan_incomplete, stop_reason = 0, 0, False, None
            unreadable_record = False
            for path in paths:
                st = path.stat()
                prior = db.execute("SELECT offset,turn_id,inode FROM checkpoint WHERE path=?", (str(path),)).fetchone()
                start, turn = (prior[0], prior[1]) if prior else (0, "")
                if prior and (st.st_ino != prior[2] or st.st_size < start):
                    db.execute("DELETE FROM message WHERE path=?", (str(path),)); start, turn = 0, ""
                with path.open("rb") as stream:
                    stream.seek(start)
                    while True:
                        offset = stream.tell()
                        remaining_bytes = max_scan_bytes - scanned_bytes
                        if remaining_bytes <= 0 or scanned_records >= 20000:
                            if offset < path.stat().st_size:
                                scan_incomplete, stop_reason = True, 'scan_budget_exhausted'
                            break
                        raw = stream.readline(min(max_line_bytes + 1, remaining_bytes))
                        scanned_bytes += len(raw)
                        if not raw:
                            break
                        if not raw.endswith(b"\n"):
                            scan_incomplete = True
                            stop_reason = ('line_exceeds_budget' if len(raw) > max_line_bytes else
                                           'scan_budget_exhausted' if len(raw) == remaining_bytes else
                                           'incomplete_append')
                            break
                        if len(raw) > max_line_bytes:
                            scan_incomplete, stop_reason = True, 'line_exceeds_budget'
                            break
                        scanned_records += 1
                        try:
                            row, payload, body = _decode_record(raw)
                        except ValueError as error:
                            scan_incomplete, unreadable_record, stop_reason = True, True, str(error)
                            break
                        if row.get("type") == "turn_context":
                            turn = payload.get("turn_id") or turn
                        elif body is not None:
                            db.execute("INSERT OR REPLACE INTO message VALUES(?,?,?,?,?,?,?)", (str(path), offset,
                                hashlib.sha256(raw).hexdigest(), payload['role'], turn, body, row.get("timestamp")))
                        start = stream.tell()
                db.execute("INSERT OR REPLACE INTO checkpoint VALUES(?,?,?,?)", (str(path), start, turn, st.st_ino))
            db.commit()
            marks = ",".join("?" for _ in paths)
            clause = f"path IN ({marks})"; args = [str(p) for p in paths]
            if turn_id:
                clause += " AND turn_id=?"; args.append(str(turn_id))
            if raw_line_sha256:
                clause += " AND hash=?"; args.append(raw_line_sha256)
            total = db.execute("SELECT count(*) FROM message WHERE " + clause, args).fetchone()[0]
            if unreadable_record:
                return {**base,"status":"source_scan_incomplete","source":{},
                        "coverage":{"matched_messages":total,"returned_messages":0,"partial":True,
                                    "scan_complete":False,"scanned_bytes":scanned_bytes,
                                    "scanned_records":scanned_records,"scan_stop_reason":stop_reason}}
            selected = db.execute("SELECT path,offset,hash,role,turn_id FROM message WHERE " + clause + " ORDER BY at DESC,path,offset DESC LIMIT 24", args).fetchall()
            text, locators, used, clipped = [], [], 0, False
            for path, offset, digest, role, turn in reversed(selected):
                with Path(path).open("rb") as stream:
                    stream.seek(offset); raw = stream.readline(max_line_bytes+1)
                if len(raw)>max_line_bytes:
                    return {**base,"status":"source_scan_incomplete","source":{},
                            "coverage":{"matched_messages":total,"returned_messages":0,"partial":True,
                                        "scan_complete":False,"scanned_bytes":scanned_bytes,
                                        "scan_stop_reason":"readback_line_exceeds_budget"}}
                if hashlib.sha256(raw).hexdigest() != digest:
                    db.execute('DELETE FROM message WHERE path=?', (path,))
                    db.execute('DELETE FROM checkpoint WHERE path=?', (path,))
                    db.commit()
                    return {**base, "status": "source_changed", "source": {}, "coverage": {"matched_messages": total}}
                try:
                    row, payload, body = _decode_record(raw)
                except ValueError as error:
                    return {**base,"status":"source_scan_incomplete","source":{},
                            "coverage":{"matched_messages":total,"returned_messages":0,"partial":True,
                                        "scan_complete":False,"scanned_bytes":scanned_bytes,
                                        "scan_stop_reason":str(error)}}
                if body is None or payload.get('role') != role:
                    db.execute('DELETE FROM message WHERE path=?', (path,))
                    db.execute('DELETE FROM checkpoint WHERE path=?', (path,))
                    db.commit()
                    return {**base,"status":"source_changed","source":{},
                            "coverage":{"matched_messages":total,"returned_messages":0,"partial":True,
                                        "scan_complete":False,"scan_stop_reason":'cache_role_mismatch' if
                                            payload.get('role') != role else 'cache_record_mismatch'}}
                # The cache locates a line; only the freshly hash-verified
                # original record supplies its text, role and timestamp.
                role, at = payload['role'], row.get('timestamp')
                remaining = max(0, int(max_chars) - used)
                if not remaining: break
                full_excerpt = f"[role: {role}; turn: {turn}; at: {at}]\n{body}"
                excerpt = full_excerpt[:remaining]
                clipped = clipped or len(excerpt) < len(full_excerpt)
                text.append(excerpt); used += len(excerpt)
                locators.append({"source_path": path, "byte_offset": offset, "raw_line_sha256": digest, "role": role, "turn_id": turn, "at": at})
            return {**base, "status": "source_read" if text else "source_scan_incomplete" if scan_incomplete else "source_empty",
                    "source": {"text": "\n\n".join(text), "locators": locators, "session_id": sid, "turn_id": turn_id, "verbatim_message_excerpts": True},
                    "coverage": {"matched_messages": total, "returned_messages": len(locators),
                                 "partial": scan_incomplete or clipped or total > len(locators),
                                 "scan_complete": not scan_incomplete, "scanned_bytes": scanned_bytes,
                                 "scanned_records": scanned_records, "scan_stop_reason": stop_reason}}
