"""Non-destructive backfill helpers for legacy recall audit traces."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .audit_trace_archive import RecallTraceArchive

BACKFILL_SCHEMA = "recall-trace-backfill.v1"


def backfill_trace(
    audit_id: str, response: Mapping[str, Any], archive: RecallTraceArchive, manifest_root: Path
) -> dict[str, Any]:
    """Archive one legacy trace and return its manifest without changing ``response``.

    Callers are intentionally responsible for database reads. This function has
    no SQL dependency and never performs an UPDATE or DELETE, making a pilot
    safe before any later retention or table-rewrite decision.
    """
    trace = response.get("trace")
    if not isinstance(trace, Mapping):
        return {"schema": BACKFILL_SCHEMA, "audit_id": str(audit_id), "status": "skipped_no_trace"}

    receipt = archive.archive_trace(trace)
    manifest = {
        "schema": BACKFILL_SCHEMA,
        "audit_id": str(audit_id),
        "status": "archived",
        "trace_archive": receipt.model_dump(),
    }
    root = Path(manifest_root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{audit_id}.json"
    temporary = target.with_suffix(".tmp")
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    temporary.write_text(payload, encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)
    return manifest
