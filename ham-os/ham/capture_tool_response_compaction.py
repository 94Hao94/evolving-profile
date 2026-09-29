"""Non-destructive envelope transformation for oversized blocked tool responses."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .adapter import _archive_tool_response

COMPACTION_SCHEMA = "ham.capture-tool-response-compaction.v1"


def compact_blocked_post_tool_event(envelope: Mapping[str, Any], capture_root: str | Path):
    """Return a compact copy plus manifest, retaining the original response in cold storage.

    The caller decides whether and how to persist this transformed envelope. No
    database writes occur here, so callers can verify the archive before any
    legacy capture row changes.
    """
    original = copy.deepcopy(dict(envelope))
    source = original.get("source_payload")
    hook = (original.get("provenance") or {}).get("hook")
    if hook != "PostToolUse" or not isinstance(source, dict) or source.get("tool_response") is None:
        return None, {"schema": COMPACTION_SCHEMA, "status": "skipped_not_post_tool_response"}

    response = source["tool_response"]
    receipt = _archive_tool_response(response, Path(capture_root), force=True)
    if receipt is None:
        raise ValueError("forced_tool_response_archive_returned_none")

    compact = copy.deepcopy(original)
    compact_source = dict(compact["source_payload"])
    compact_source.pop("tool_response", None)
    compact_source["tool_response_archive"] = receipt
    compact["source_payload"] = compact_source
    original_body = str(compact.get("body_text") or "")
    compact["body_text"] = original_body[:4096]
    compact["body_preview"] = str(compact.get("body_preview") or original_body[:4096])[:4096]
    compact["body_ref"] = receipt
    provenance = dict(compact.get("provenance") or {})
    provenance["body_evidence"] = "archived_supplied_tool_response"
    compact["provenance"] = provenance

    manifest = {
        "schema": COMPACTION_SCHEMA,
        "status": "archived",
        "event_id": compact.get("event_id"),
        "original_envelope_sha256": hashlib.sha256(
            json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "original_response_sha256": receipt["sha256"],
        "tool_response_archive": receipt,
    }
    return compact, manifest
