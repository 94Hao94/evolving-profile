"""Strict, dependency-free contracts for source-backed guidance."""
from __future__ import annotations

from hashlib import sha256
import json
import uuid


CATEGORIES = {"communication", "learning", "reasoning", "collaboration", "delivery"}
NATURES = {"declared_preference", "explicit_requirement", "inferred_pattern", "task_local"}
POLARITIES = {"prefer", "avoid", "require", "forbid", "neutral"}
SCOPE_LEVELS = {"global", "domain", "project", "task"}
VALIDITY_KINDS = {"stable", "context_sensitive", "volatile_method"}
REVIEW_FIELDS = {
    "support", "scope_ok", "conditions_preserved", "source_role_ok", "hypothetical_only",
    "conflicts", "source_witness_hash", "reviewer_model", "reviewed_at",
}


def canonical_sha256(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def review_contract_accepts(review: object) -> bool:
    if not isinstance(review, dict) or not REVIEW_FIELDS.issubset(review):
        return False
    return (review["support"] == "supported" and review["scope_ok"] is True and
            review["conditions_preserved"] is True and review["source_role_ok"] is True and
            review["hypothetical_only"] is False and isinstance(review["conflicts"], list) and
            not review["conflicts"] and all(isinstance(review[field], str) and review[field]
                                             for field in ("source_witness_hash", "reviewer_model", "reviewed_at")))


def _source_error(ref: object) -> str | None:
    if not isinstance(ref, dict):
        return "invalid_evidence_ref"
    required = ("bank_id", "document_id", "source_revision", "source_sha256", "quote", "stored_role", "origin",
                "statement_kind", "stored_at", "origin_witness_ref", "origin_witness_sha256")
    if any(not isinstance(ref.get(key), str) or not ref[key] for key in required):
        return "incomplete_evidence_ref"
    if ref.get("memory_id") is not None:
        try:
            uuid.UUID(str(ref["memory_id"]))
        except ValueError:
            return "invalid_memory_id"
    if not (isinstance(ref.get("span_start"), int) and isinstance(ref.get("span_end"), int) and
            0 <= ref["span_start"] < ref["span_end"]):
        return "invalid_source_span"
    if ref["statement_kind"] == "hypothetical":
        return "hypothetical_not_assertion"
    if ref["origin"] in {"test_probe", "agent_generated", "unknown"}:
        return "source_origin_not_eligible"
    if ref["stored_role"] != "user":
        return "source_role_not_eligible"
    return None


def validate_proposal(proposal: object) -> dict:
    if not isinstance(proposal, dict):
        return {"status": "rejected", "reason": "proposal_not_object"}
    required = ("proposal_id", "operation", "nature", "primary_category", "text", "applies_when", "exceptions",
                "effect_on_action", "scope", "evidence_refs", "source_family_ids")
    if any(key not in proposal for key in required):
        return {"status": "rejected", "reason": "missing_proposal_field"}
    if proposal["nature"] not in NATURES or proposal["primary_category"] not in CATEGORIES:
        return {"status": "rejected", "reason": "invalid_guidance_classification"}
    structured = ("preference_kind", "polarity", "scope_level", "validity_kind", "confidence_inputs",
                  "support_count", "contradiction_count", "source_turn_ids", "supersedes", "superseded_by", "cross_cutting")
    missing_structured = [key for key in structured if key not in proposal]
    if missing_structured and proposal["nature"] == "inferred_pattern":
        return {"status": "held", "reason": "missing_structured_preference_fields"}
    if not missing_structured:
        if proposal["polarity"] not in POLARITIES or proposal["scope_level"] not in SCOPE_LEVELS or proposal["validity_kind"] not in VALIDITY_KINDS:
            return {"status": "rejected", "reason": "invalid_guidance_lifecycle_classification"}
        if not isinstance(proposal["preference_kind"], str) or not proposal["preference_kind"].strip():
            return {"status": "rejected", "reason": "invalid_preference_kind"}
        if not isinstance(proposal["confidence_inputs"], dict) or not isinstance(proposal["cross_cutting"], bool):
            return {"status": "rejected", "reason": "invalid_guidance_quality_fields"}
        if any(not isinstance(proposal[key], int) or proposal[key] < 0 for key in ("support_count", "contradiction_count")):
            return {"status": "rejected", "reason": "invalid_guidance_evidence_counts"}
        if any(not isinstance(proposal[key], list) for key in ("source_turn_ids", "supersedes", "superseded_by")):
            return {"status": "rejected", "reason": "invalid_guidance_lifecycle_lists"}
    if not isinstance(proposal["text"], str) or not proposal["text"].strip():
        return {"status": "rejected", "reason": "empty_guidance_text"}
    if not all(isinstance(proposal[key], list) for key in ("applies_when", "exceptions", "evidence_refs", "source_family_ids")):
        return {"status": "rejected", "reason": "invalid_list_field"}
    scope = proposal["scope"]
    if not isinstance(scope, dict) or not isinstance(scope.get("user_id"), str) or not scope["user_id"]:
        return {"status": "rejected", "reason": "invalid_guidance_scope"}
    if proposal["nature"] == "task_local" and not scope.get("task_ids"):
        return {"status": "rejected", "reason": "task_local_requires_task_id"}
    if not proposal["evidence_refs"]:
        return {"status": "held", "reason": "missing_evidence"}
    if proposal["nature"] == "inferred_pattern" and (
        proposal.get("support_count", 0) < 2 or len(set(proposal["source_family_ids"])) < 2
    ):
        return {"status": "held", "reason": "inferred_preference_requires_independent_support"}
    for ref in proposal["evidence_refs"]:
        reason = _source_error(ref)
        if reason:
            return {"status": "held" if reason != "invalid_memory_id" else "rejected", "reason": reason}
    if len(set(proposal["source_family_ids"])) != len(proposal["source_family_ids"]):
        return {"status": "rejected", "reason": "duplicate_source_family"}
    return {"status": "supported", "reason": "source_contract_valid", "proposal_sha256": canonical_sha256(proposal)}
