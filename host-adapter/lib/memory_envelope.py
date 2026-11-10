"""Shared governance envelope for every EP memory family.

The envelope is deliberately orthogonal to memory content.  Entity, fact,
experience, preference, process and working-state records can keep their own
payload while sharing the same scope, provenance, verification and lifecycle
fields.  This keeps the model extensible without adding another content type
for every dimension discovered in a host integration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


SCHEMA = "evolving-profile.memory-envelope.v1"
KINDS = {
    "entity", "fact", "experience", "preference", "working_state",
    "procedure", "outcome", "evidence", "artifact", "observation",
    "process", "trace", "event", "episode", "pattern", "skill",
}
SCOPE_KINDS = {"user", "project", "session", "task", "host", "agent", "global"}
VERIFICATION_STATES = {
    "unverified", "observed", "source_checked", "verified", "conflicted",
    "superseded", "rejected",
}


class MemoryEnvelopeError(ValueError):
    """Raised when a memory envelope cannot be safely normalized."""


def _string(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise MemoryEnvelopeError(f"memory_envelope_{field}_required")
        return None
    result = str(value).strip()
    if not result:
        if required:
            raise MemoryEnvelopeError(f"memory_envelope_{field}_required")
        return None
    return result


def _timestamp(value: Any, field: str) -> str | None:
    result = _string(value, field)
    if result is None:
        return None
    candidate = result.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise MemoryEnvelopeError(f"memory_envelope_{field}_invalid") from exc
    return result


def _scope(value: Any) -> dict[str, str | None]:
    if isinstance(value, str):
        value = {"kind": value}
    if not isinstance(value, dict):
        raise MemoryEnvelopeError("memory_envelope_scope_invalid")
    kind = _string(value.get("kind"), "scope_kind", required=True)
    if kind not in SCOPE_KINDS:
        raise MemoryEnvelopeError("memory_envelope_scope_kind_invalid")
    identifier = _string(value.get("id"), "scope_id")
    return {"kind": kind, "id": identifier}


def _refs(value: Any, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise MemoryEnvelopeError(f"memory_envelope_{field}_invalid")
    result: list[Any] = []
    for item in value:
        if isinstance(item, (str, int, float)) and str(item).strip():
            result.append(str(item).strip())
        elif isinstance(item, dict) and item:
            result.append(dict(item))
        else:
            raise MemoryEnvelopeError(f"memory_envelope_{field}_item_invalid")
    return result


def _list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise MemoryEnvelopeError(f"memory_envelope_{field}_invalid")
    result = [str(item).strip() for item in value if str(item).strip()]
    return result


def normalize_memory_envelope(record: dict[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical, backward-compatible envelope.

    ``record`` may contain content-specific fields.  They are preserved so the
    envelope can be embedded in existing entity/fact/process rows without a
    storage migration.  Unknown governance fields are retained as supplied;
    known fields are normalized and validated fail-closed.
    """
    if not isinstance(record, dict):
        raise MemoryEnvelopeError("memory_envelope_invalid")
    value = dict(record)
    kind = _string(value.get("kind"), "kind", required=True)
    if kind not in KINDS:
        raise MemoryEnvelopeError("memory_envelope_kind_invalid")

    value["schema"] = str(value.get("schema") or SCHEMA)
    value["kind"] = kind
    value["scope"] = _scope(value.get("scope") or {"kind": "global"})
    value["audience"] = _list(value.get("audience"), "audience")
    value["source_refs"] = _refs(value.get("source_refs"), "source_refs")
    value["artifact_refs"] = _refs(value.get("artifact_refs"), "artifact_refs")
    value["supersedes"] = _refs(value.get("supersedes"), "supersedes")
    value["superseded_by"] = _refs(value.get("superseded_by"), "superseded_by")
    value["source_type"] = _string(value.get("source_type"), "source_type")
    value["verification_state"] = _string(value.get("verification_state"), "verification_state") or "unverified"
    if value["verification_state"] not in VERIFICATION_STATES:
        raise MemoryEnvelopeError("memory_envelope_verification_state_invalid")

    confidence = value.get("confidence")
    if confidence is not None:
        if isinstance(confidence, bool):
            raise MemoryEnvelopeError("memory_envelope_confidence_invalid")
        try:
            confidence = float(confidence)
        except (TypeError, ValueError) as exc:
            raise MemoryEnvelopeError("memory_envelope_confidence_invalid") from exc
        if confidence < 0.0 or confidence > 1.0:
            raise MemoryEnvelopeError("memory_envelope_confidence_out_of_range")
        value["confidence"] = confidence
    else:
        value["confidence"] = None

    for field in ("observed_at", "event_time", "valid_from", "valid_to", "last_used_at"):
        value[field] = _timestamp(value.get(field), field)
    value["consent_state"] = _string(value.get("consent_state"), "consent_state")
    value["retention_policy"] = dict(value.get("retention_policy") or {})
    value["outcome"] = value.get("outcome") if isinstance(value.get("outcome"), dict) else (
        {"status": str(value["outcome"])} if value.get("outcome") not in (None, "") else None
    )
    for field in ("host_id", "installation_id", "session_id", "turn_id", "task_id", "content_ref"):
        value[field] = _string(value.get(field), field)
    utility = value.get("utility")
    if utility is not None:
        try:
            utility = float(utility)
        except (TypeError, ValueError) as exc:
            raise MemoryEnvelopeError("memory_envelope_utility_invalid") from exc
        value["utility"] = utility
    else:
        value["utility"] = None
    return value


def validate_memory_envelope(record: dict[str, Any]) -> bool:
    """Return ``True`` only when ``record`` satisfies the envelope contract."""
    normalize_memory_envelope(record)
    return True

