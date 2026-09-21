"""Persisted incremental-state helpers; provider calls remain isolated from publication."""
from __future__ import annotations

from hashlib import sha256
import json
import time


def job_id(bank_id: str, source_family: str, source_revision: str, pipeline_version: str, operation: str) -> str:
    return "sha256:" + sha256("\x1f".join((bank_id, source_family, source_revision, pipeline_version, operation)).encode()).hexdigest()


def settle_snapshot(job: dict) -> dict:
    seen = list(dict.fromkeys(job.get("seen") or []))
    processed = list(dict.fromkeys(job.get("processed") or []))
    remaining = [event for event in seen if event not in set(processed)]
    return {"remaining": remaining, "complete": not remaining, "processed": processed,
            "last_processed_event": processed[-1] if processed else None, "last_seen_event": seen[-1] if seen else None}


def record_provider_block(repo, provider: str, reason: str, events: list[dict]) -> str:
    payload = {"provider": provider, "reason": reason, "events": events, "blocked_at": time.time(), "llm_calls": 0}
    return repo.record_job("incremental", "blocked_provider", payload)


def validate_provider_proposal(output: dict, known_event_ids: set[str]) -> dict:
    if not isinstance(output, dict) or output.get("schema") != "guidance.proposal.v1":
        return {"ok": False, "reason": "invalid_provider_schema"}
    if not isinstance(output.get("changes"), list) or not isinstance(output.get("unresolved"), list):
        return {"ok": False, "reason": "invalid_provider_shape"}
    for change in output["changes"]:
        if not isinstance(change, dict) or not set(change.get("source_event_ids") or []).issubset(known_event_ids):
            return {"ok": False, "reason": "foreign_or_missing_source_event"}
    return {"ok": True, "reason": "provider_output_is_candidate_only"}
