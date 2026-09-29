"""Deterministic Session/Project association migration for Bank exports."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


def project_key(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16] if value else ""


def write_association_snapshot(path: str | Path, payload: dict) -> dict:
    """Replace a read-only association sidecar only after the scan completes."""
    links = payload.get("links")
    if not isinstance(links, list) or not isinstance(payload.get("scanned_records"), int):
        raise ValueError("invalid_association_snapshot")
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return {"path": str(target), "scanned_records": payload["scanned_records"], "linked_records": len(links)}


def associate_records(records, contexts):
    sessions = {str(row.get("session_id")): row for row in contexts.get("sessions", []) if row.get("session_id")}
    projects = {str(row.get("project_key")): row for row in contexts.get("projects", []) if row.get("project_key")}
    links, unresolved = [], []
    for record in records or []:
        if not isinstance(record, dict) or not record.get("id"):
            continue
        metadata = record.get("metadata") or {}
        ids = metadata.get("session_ids") or metadata.get("session_id") or []
        if isinstance(ids, str):
            ids = [value.strip() for value in ids.split(",") if value.strip()]
        session_ids = [str(value) for value in ids if str(value) in sessions]
        raw_project = metadata.get("project") or metadata.get("cwd") or ""
        pkey = str(metadata.get("project_key") or project_key(raw_project))
        matched_project = pkey if pkey in projects else ""
        if not session_ids and not matched_project:
            unresolved.append({"record_id": str(record["id"]), "reason": "scope_metadata_missing_or_unmatched"})
            continue
        links.append({
            "record_id": str(record["id"]),
            "record_type": str(record.get("type") or "unknown"),
            "session_ids": session_ids,
            "project_key": matched_project or None,
            "status": "inferred" if not metadata.get("project_key") else "metadata_matched",
            "source_ids": list(record.get("source_ids") or [str(record.get("id"))]),
        })
    return {"schema": "evolving-profile.context-associations.v1", "links": links, "unresolved": unresolved,
            "policy": "association_only_no_fact_rewrite"}
