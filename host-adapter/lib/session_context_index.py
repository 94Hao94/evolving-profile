"""Incremental, evidence-preserving index for large Codex rollout JSONL files.

The raw rollout is the source of truth and is intentionally never rewritten.
This sidecar stores only user messages and final assistant answers with the
byte offset that points back to the original JSONL.  It lets a Hook assemble a
small, inspectable context evidence pack without parsing a multi-GB compacted
history synchronously on every user turn.
"""

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

from .content import extract_user_request, is_synthetic_codex_user_message


DEFAULT_INDEX_PATH = os.path.expanduser(
    "~/.evolving-profile/audit/session-context-index.sqlite"
)
_MAX_TURN_CHARS = 12000
_CJK = re.compile(r"[\u3400-\u9fff]")
_WORDS = re.compile(r"[a-z0-9][a-z0-9_+.-]{1,}", re.I)


def _connect(index_path):
    directory = os.path.dirname(os.path.abspath(index_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    connection = sqlite3.connect(index_path, timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_checkpoint (
          source_path TEXT PRIMARY KEY,
          file_size INTEGER NOT NULL DEFAULT 0,
          mtime_ns INTEGER NOT NULL DEFAULT 0,
          byte_offset INTEGER NOT NULL DEFAULT 0,
          last_hash TEXT,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS session_turn (
          id INTEGER PRIMARY KEY,
          source_path TEXT NOT NULL,
          byte_offset INTEGER NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          event_time TEXT,
          UNIQUE(source_path, byte_offset, content_hash)
        );
        CREATE INDEX IF NOT EXISTS session_turn_source_id
          ON session_turn(source_path, id);
        """
    )
    return connection


def _text_from_entry(entry):
    """Return (role, text, timestamp) for one durable chat turn, if any."""
    if not isinstance(entry, dict):
        return None
    if "role" in entry and "content" in entry:
        role = entry.get("role")
        text = entry.get("content")
        if isinstance(text, list):
            text = "\n".join(
                str(block.get("text") or "")
                for block in text if isinstance(block, dict)
            )
        return role, str(text or ""), entry.get("timestamp")
    if entry.get("type") != "response_item":
        return None
    payload = entry.get("payload") or {}
    if payload.get("type") != "message":
        return None
    role = payload.get("role")
    if role not in ("user", "assistant"):
        return None
    if role == "assistant" and payload.get("phase") not in {"final_answer", "final"}:
        return None
    parts = []
    for block in payload.get("content") or []:
        if isinstance(block, dict) and block.get("type") in ("input_text", "output_text", "text"):
            value = str(block.get("text") or "").strip()
            if value:
                parts.append(value)
    return role, "\n".join(parts), entry.get("timestamp")


def _normalise_turn(role, text):
    value = str(text or "").strip()
    if role == "user":
        if is_synthetic_codex_user_message(value):
            return ""
        value = extract_user_request(value)
    return value.strip()[:_MAX_TURN_CHARS]


def index_transcript(transcript_path, index_path=DEFAULT_INDEX_PATH, rebuild=False,
                     bootstrap_tail_bytes=None):
    """Append new transcript turns to the sidecar index.

    For a first live Hook `bootstrap_tail_bytes` makes indexing start at the
    tail rather than parsing historical compaction snapshots.  A detached
    backfill can later call this function with `rebuild=True`; that full pass
    is outside the latency-sensitive Hook path.
    """
    source_path = os.path.abspath(os.path.expanduser(str(transcript_path or "")))
    if not os.path.isfile(source_path):
        return {"ok": False, "reason": "transcript_missing", "indexed_messages": 0}
    stat = os.stat(source_path)
    connection = _connect(index_path)
    try:
        if rebuild:
            connection.execute("DELETE FROM session_turn WHERE source_path = ?", (source_path,))
            connection.execute("DELETE FROM source_checkpoint WHERE source_path = ?", (source_path,))
            connection.commit()
        row = connection.execute(
            "SELECT byte_offset FROM source_checkpoint WHERE source_path = ?", (source_path,)
        ).fetchone()
        start_offset = int(row[0]) if row else 0
        bootstrap = False
        if not row and bootstrap_tail_bytes and stat.st_size > int(bootstrap_tail_bytes):
            start_offset = max(0, stat.st_size - int(bootstrap_tail_bytes))
            bootstrap = True
        if start_offset > stat.st_size:
            # Source was rotated or truncated: preserve old evidence but start
            # indexing the new file from its beginning.
            start_offset = 0
        indexed = 0
        last_hash = ""
        with open(source_path, "rb") as handle:
            if start_offset:
                handle.seek(start_offset - 1)
                at_line_start = handle.read(1) == b"\n"
                if not at_line_start:
                    handle.readline()  # only a tail bootstrap can start mid-row
            checkpoint_offset = handle.tell()
            while True:
                offset = handle.tell()
                raw = handle.readline()
                if not raw:
                    break
                # The active writer can be midway through a JSONL record.
                # Retry that entire record on the next incremental pass.
                if not raw.endswith(b"\n"):
                    break
                checkpoint_offset = handle.tell()
                try:
                    entry = json.loads(raw.decode("utf-8", errors="replace"))
                except (ValueError, UnicodeError):
                    continue
                parsed = _text_from_entry(entry)
                if not parsed:
                    continue
                role, text, event_time = parsed
                text = _normalise_turn(role, text)
                if not text:
                    continue
                content_hash = hashlib.sha256((role + "\0" + text).encode("utf-8")).hexdigest()
                connection.execute(
                    "INSERT OR IGNORE INTO session_turn "
                    "(source_path, byte_offset, role, content, content_hash, event_time) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (source_path, offset, role, text, content_hash, event_time),
                )
                indexed += 1
                last_hash = content_hash
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO source_checkpoint "
            "(source_path,file_size,mtime_ns,byte_offset,last_hash,updated_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(source_path) DO UPDATE SET file_size=excluded.file_size, "
            "mtime_ns=excluded.mtime_ns, byte_offset=excluded.byte_offset, "
            "last_hash=excluded.last_hash, updated_at=excluded.updated_at",
            (source_path, stat.st_size, stat.st_mtime_ns, checkpoint_offset, last_hash, now),
        )
        connection.commit()
        total = connection.execute(
            "SELECT COUNT(*) FROM session_turn WHERE source_path = ?", (source_path,)
        ).fetchone()[0]
        return {"ok": True, "indexed_messages": indexed, "indexed_total": int(total),
                "source_path": source_path, "bootstrap_tail": bootstrap,
                "checkpoint_offset": checkpoint_offset}
    finally:
        connection.close()


def _terms(value):
    text = str(value or "").casefold()
    terms = set(_WORDS.findall(text))
    cjk = "".join(_CJK.findall(text))
    terms.update(cjk[index:index + 2] for index in range(max(0, len(cjk) - 1)))
    if len(cjk) == 1:
        terms.add(cjk)
    return {term for term in terms if len(term) >= 2}


def _score(query_terms, content, recency_rank):
    candidate_terms = _terms(content)
    overlap = len(query_terms & candidate_terms)
    if not overlap:
        return 0.0
    # The lexical evidence is deterministic.  A small recency term resolves
    # ties without allowing a recent unrelated turn to win.
    return overlap * 10.0 + min(2.0, recency_rank / 10000.0)


def _clip(value, maximum):
    encoded = str(value or "").encode("utf-8")
    if len(encoded) <= maximum:
        return str(value or "")
    return encoded[:maximum].decode("utf-8", errors="ignore").rstrip() + "…"


def retrieve_context_bundle(prompt, index_path=DEFAULT_INDEX_PATH, source_path=None,
                            recent_limit=8, older_limit=8, max_bytes=28000):
    """Return a bounded, source-addressable context evidence pack.

    `recent` preserves conversational continuity.  `older_matches` is a
    hybrid lexical/entity-safe fallback over the compact sidecar, not the raw
    multi-GB rollout.  Each row retains its raw JSONL byte offset for UI audit.
    """
    if not os.path.isfile(index_path):
        return {"recent": [], "older_matches": [], "messages": [], "rendered_context": "",
                "receipt": {"strategy": "session_index_unavailable", "index_messages": 0}}
    source_path = os.path.abspath(os.path.expanduser(str(source_path))) if source_path else None
    connection = _connect(index_path)
    try:
        if source_path:
            rows = connection.execute(
                "SELECT id,source_path,byte_offset,role,content,event_time FROM session_turn "
                "WHERE source_path = ? ORDER BY id DESC", (source_path,)
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT id,source_path,byte_offset,role,content,event_time FROM session_turn ORDER BY id DESC"
            ).fetchall()
    finally:
        connection.close()
    recent_rows = list(reversed(rows[:max(0, int(recent_limit))]))
    recent_ids = {row[0] for row in recent_rows}
    query_terms = _terms(prompt)
    scored = []
    for position, row in enumerate(rows[int(recent_limit):], start=1):
        score = _score(query_terms, row[4], len(rows) - position)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda value: (-value[0], -value[1][0]))
    older_rows = [row for _, row in scored[:max(0, int(older_limit))] if row[0] not in recent_ids]

    def serialise(row):
        return {"id": row[0], "source_path": row[1], "byte_offset": row[2],
                "role": row[3], "content": row[4], "event_time": row[5]}
    recent = [serialise(row) for row in recent_rows]
    older = [serialise(row) for row in older_rows]
    selected = older + recent
    messages = [{"role": item["role"], "content": _clip(item["content"], 5000)} for item in selected]
    lines = ["[会话索引证据包：每条可回到原始 JSONL 偏移]"]
    for item in selected:
        prefix = "较早相关" if item in older else "最近上下文"
        lines.append("%s @%s %s: %s" % (
            prefix, item["byte_offset"], item["role"], _clip(item["content"], 2500)))
    rendered = _clip("\n".join(lines), int(max_bytes))
    return {
        "recent": recent, "older_matches": older, "messages": messages,
        "rendered_context": rendered,
        "receipt": {
            "strategy": "session_index_recent_plus_lexical_evidence",
            "source_path": source_path,
            "index_messages": len(rows), "recent_count": len(recent),
            "older_match_count": len(older), "candidate_count": len(scored),
            "rendered_bytes": len(rendered.encode("utf-8")),
            "selected_turns": [
                {"id": item["id"], "byte_offset": item["byte_offset"], "role": item["role"]}
                for item in selected
            ],
        },
    }
