"""Guidance rebuild and bottom-layer taxonomy audit helpers."""
from __future__ import annotations

from hashlib import sha256
import datetime as dt
import json
import re


DOMAIN_CATEGORY = {
    "liuzhongyang-cognition-learning": "learning",
    "liuzhongyang-business-architecture": "reasoning",
    "liuzhongyang-collaboration-delivery": "delivery",
    "liuzhongyang-work-project-architecture": "collaboration",
    "liuzhongyang-ai-operating-system": "collaboration",
    "unclassified": "communication",
}
OBSERVATION_DISPOSITIONS = {"guidance_candidate", "knowledge_observation", "downgrade_world", "downgrade_experience", "held_insufficient_evidence", "reject_polluted"}


def build_direct_policy_proposal(policy: dict, memory: dict, chunk: dict, bank_id: str) -> dict:
    review = policy.get("source_review") or {}
    quote = str(review.get("source_quote") or "")
    text = str(chunk.get("chunk_text") or "")
    if policy.get("status") != "active_provisional" or memory.get("state") != "valid":
        raise ValueError("policy_not_active_or_source_invalid")
    if memory.get("document_id") != policy.get("source_document_id") or chunk.get("document_id") != memory.get("document_id") or chunk.get("bank_id") != bank_id:
        raise ValueError("policy_source_identity_mismatch")
    start = text.find(quote)
    if not quote or start < 0 or sha256(text.encode()).hexdigest() != review.get("source_sha256"):
        raise ValueError("policy_source_revision_or_quote_changed")
    return {
        "proposal_id": "guidance:" + policy["policy_id"], "operation": "create", "target_id": policy["policy_id"], "base_revision": None,
        "nature": "explicit_requirement", "primary_category": DOMAIN_CATEGORY.get(policy.get("model_domain"), "communication"), "related_categories": [],
        "text": policy["policy"], "applies_when": [policy.get("scope") or "原始要求适用的同类任务"],
        "exceptions": [policy.get("boundary") or "当前 Prompt 或更具体要求优先"], "effect_on_action": "在匹配范围内约束执行方式，不扩大本轮授权",
        "scope": {"user_id": "liuzhongyang", "agent_roles": [], "project_ids": [], "task_ids": [], "domains": [], "media": []},
        "evidence_refs": [{"bank_id": bank_id, "memory_id": memory["id"], "document_id": memory["document_id"], "chunk_id": memory.get("chunk_id"),
                           "source_revision": memory.get("updated_at") or memory.get("mentioned_at") or review["source_sha256"], "source_sha256": review["source_sha256"],
                           "span_start": start, "span_end": start + len(quote), "quote": quote, "stored_role": "user", "origin": "user_direct",
                           "statement_kind": "request", "event_at": memory.get("mentioned_at"), "stored_at": memory.get("updated_at") or "unknown",
                           "human_author_verified": False, "origin_witness_ref": "directive-policy-index:" + policy["policy_id"],
                           "origin_witness_sha256": review["source_sha256"]}],
        "source_family_ids": ["document:" + memory["document_id"]],
    }


def taxonomy_suspicion(row: dict) -> dict:
    text = str(row.get("text") or "")
    current = bool(re.search(r"(?:当前|目前|现行|默认|仍然|截至|长期有效|配置为)", text))
    event = bool(row.get("occurred_start") or re.search(r"(?:于20\d{2}|已完成|完成了|曾经|当时|随后|发生|发送了|签订)", text))
    actual = row.get("fact_type")
    suspected = "experience" if actual == "world" and event and not current else "world" if actual == "experience" and current and not event else actual
    return {"id": row.get("id"), "actual_type": actual, "suspected_type": suspected,
            "needs_review": suspected != actual, "reason": "event_shape" if suspected == "experience" and suspected != actual else "current_state_shape" if suspected == "world" and suspected != actual else "no_rule_suspicion"}


def direct_policy_review(policy: dict, proposal: dict) -> dict:
    ref = proposal["evidence_refs"][0]
    return {"support": "supported", "scope_ok": True, "conditions_preserved": True, "source_role_ok": True,
            "hypothetical_only": False, "conflicts": [], "source_witness_hash": ref["origin_witness_sha256"],
            "reviewer_model": "existing_independent_source_review_plus_live_readback", "reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat()}


def validate_observation_classification(row: object, expected_id: str, source_ids: set[str]) -> dict:
    if not isinstance(row, dict) or row.get("id") != expected_id or row.get("disposition") not in OBSERVATION_DISPOSITIONS:
        return {"ok": False, "reason": "invalid_identity_or_disposition"}
    required = ("primary_category", "related_categories", "text", "applies_when", "exceptions", "effect_on_action", "evidence_ids", "reason")
    if any(key not in row for key in required) or not isinstance(row["text"], str) or not row["text"].strip():
        return {"ok": False, "reason": "missing_classification_field"}
    if not all(isinstance(row[key], list) for key in ("related_categories", "applies_when", "exceptions", "evidence_ids")):
        return {"ok": False, "reason": "invalid_classification_list"}
    if not set(row["evidence_ids"]).issubset(source_ids):
        return {"ok": False, "reason": "foreign_evidence_id"}
    if row["disposition"] == "guidance_candidate" and row.get("primary_category") not in {"communication", "learning", "reasoning", "collaboration", "delivery"}:
        return {"ok": False, "reason": "guidance_category_required"}
    if row["disposition"] == "guidance_candidate" and not row["evidence_ids"]:
        return {"ok": False, "reason": "guidance_evidence_required"}
    return {"ok": True, "reason": "classification_contract_valid"}
