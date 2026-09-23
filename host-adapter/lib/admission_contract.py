"""Pure, versioned bindings between a candidate and one admission decision.

This module deliberately does not read a Bank, configuration, or network
resource.  It lets the Controller make a semantic decision once and gives the
Hook enough evidence to decide whether that decision still belongs to the same
turn and source revision.
"""
from __future__ import annotations

import hashlib
from typing import Any


SCHEMA = "hindsight.admission_contract.v1"
ACTIONS = {"admit", "reject", "defer"}
CONTEXT_FIELDS = (
    "session_id",
    "turn_id",
    "hook_invocation_id",
    "execution_id",
    "prompt_sha256",
    "policy_version",
    "source_revision",
)


def content_sha256(text: str) -> str:
    """Hash the exact candidate content; formatting is part of its identity."""
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _record_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("chunk_id") or "")


def _record_type(item: dict[str, Any]) -> str:
    return str(item.get("type") or "").strip().casefold()


def _content(item: dict[str, Any]) -> str:
    return str(item.get("text") or item.get("content") or "")


def decision_key(item: dict[str, Any]) -> str:
    """Return an opaque identity for one typed, exact-content candidate."""
    material = "\x1f".join((_record_id(item), _record_type(item), content_sha256(_content(item))))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _binding(context: dict[str, Any]) -> dict[str, str]:
    return {field: str(context.get(field) or "") for field in CONTEXT_FIELDS}


def make_decision(
    item: dict[str, Any], context: dict[str, Any], action: str, reason: str,
    *, reason_detail: str = "", decider: str = "controller",
) -> dict[str, Any]:
    """Create a decision that the Hook can verify without re-scoring content."""
    action = str(action or "").strip().casefold()
    if action not in ACTIONS:
        raise ValueError("action must be admit, reject, or defer")
    missing = [field for field, value in _binding(context).items() if not value]
    if missing:
        raise ValueError("binding requires " + ", ".join(missing))
    record_id, record_type, text = _record_id(item), _record_type(item), _content(item)
    if not record_id or not record_type:
        raise ValueError("item requires a non-empty id and type")
    return {
        "schema": SCHEMA,
        "decision_key": decision_key(item),
        "record_id": record_id,
        "record_type": record_type,
        "content_sha256": content_sha256(text),
        "binding": _binding(context),
        "action": action,
        "reason": str(reason or "unspecified"),
        "reason_detail": str(reason_detail or ""),
        "decider": str(decider or "controller"),
    }


def validate_decision(
    item: dict[str, Any], decision: dict[str, Any], context: dict[str, Any]
) -> tuple[bool, str]:
    """Verify that a Controller decision can safely be reused in this turn."""
    if not isinstance(decision, dict) or decision.get("schema") != SCHEMA:
        return False, "legacy_unverified"
    if str(decision.get("decision_key") or "") != decision_key(item):
        return False, "candidate_mismatch"
    if str(decision.get("record_id") or "") != _record_id(item):
        return False, "record_mismatch"
    if str(decision.get("record_type") or "") != _record_type(item):
        return False, "record_type_mismatch"
    if str(decision.get("content_sha256") or "") != content_sha256(_content(item)):
        return False, "content_mismatch"
    if decision.get("action") not in ACTIONS:
        return False, "invalid_action"
    if not isinstance(decision.get("binding"), dict):
        return False, "binding_missing"
    if any(not value for value in decision["binding"].values()):
        return False, "binding_incomplete"
    if decision["binding"] != _binding(context):
        return False, "context_mismatch"
    return True, "matched"


def partition_verified_decisions(
    items: list[dict[str, Any]], decisions: list[dict[str, Any]], context: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """Separate Controller decisions without re-running semantic relevance.

    A missing, duplicate, or context-mismatched decision remains unverified so
    the caller can use the explicit legacy/shadow path. It must not silently
    become a new Hook-side semantic rejection.
    """
    by_key: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for raw in decisions or []:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("decision_key") or "")
        if not key:
            continue
        if key in by_key:
            duplicates.add(key)
            continue
        by_key[key] = raw
    result = {"admit": [], "reject": [], "defer": [], "unverified": []}
    for raw in items or []:
        item = dict(raw or {})
        key = decision_key(item)
        decision = by_key.get(key)
        if key in duplicates or decision is None or not validate_decision(item, decision, context)[0]:
            result["unverified"].append(item)
            continue
        result[str(decision["action"])].append(item)
    return result
