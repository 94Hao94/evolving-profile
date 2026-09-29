"""Bounded original Session transcript input for Scenario Summary drafts."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from .content import extract_user_request, read_transcript


NORMALIZATION_VERSION = "scenario-source-v2"


def revision_for_messages(messages: list[dict]) -> str:
    canonical = [{"raw_line_sha256": item.get("raw_line_sha256"), "role": item.get("role"),
                  "text": item.get("text"), "turn_id": item.get("turn_id")}
                 for item in messages]
    payload = {"normalization_version": NORMALIZATION_VERSION, "messages": canonical}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def read_session_source(thread_id: str, session_root: str | Path, *, max_chars: int = 30000) -> dict:
    identity = str(uuid.UUID(str(thread_id)))
    if type(max_chars) is not int or max_chars < 1:
        raise ValueError("max_chars_must_be_positive")
    root = Path(session_root).expanduser()
    paths = sorted(root.rglob(f"rollout-*-{identity}.jsonl")) if root.is_dir() else []
    base = {"thread_id": identity, "source": "codex_thread_history", "source_files": [str(path) for path in paths],
            "coverage": "visible_user_and_final_assistant_messages_only_not_tool_outputs", "messages": []}
    if not paths:
        return {**base, "status": "source_missing", "total_chars": 0, "user_count": 0, "assistant_count": 0, "source_revision": None}
    if len(paths) > 8:
        return {**base, "status": "too_many_source_files", "total_chars": 0, "user_count": 0, "assistant_count": 0, "source_revision": None}

    messages = []
    for path in paths:
        for item in read_transcript(str(path)):
            role = item.get("role")
            text = str(item.get("content") or "").strip()
            if role == "user":
                text = extract_user_request(text)
            source_record = item.get("source_record") or {}
            if role not in {"user", "assistant"} or not text:
                continue
            raw_hash = str(source_record.get("raw_line_sha256") or "")
            if not raw_hash:
                continue
            messages.append({"evidence_id": raw_hash[:16], "role": role, "text": text,
                             "turn_id": source_record.get("turn_id"), "at": source_record.get("recorded_at"),
                             "source_path": str(path), "byte_offset": source_record.get("byte_offset"),
                             "raw_line_sha256": raw_hash})
    for position, item in enumerate(messages, start=1):
        item["model_ref"] = f"m{position}"
    total_chars = sum(len(item["text"]) for item in messages)
    digest = revision_for_messages(messages) if messages else None
    result = {**base, "total_chars": total_chars, "user_count": sum(item["role"] == "user" for item in messages),
              "assistant_count": sum(item["role"] == "assistant" for item in messages), "source_revision": digest}
    if not messages:
        return {**result, "status": "source_empty"}
    if total_chars > max_chars:
        return {**result, "status": "over_budget"}
    return {**result, "status": "complete", "messages": messages}
