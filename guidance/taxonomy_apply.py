"""Fail-closed application rules for world/experience reclassification."""
from __future__ import annotations

from hashlib import sha256


def eligible_change(current: dict, decision: dict) -> dict:
    if current.get("id") != decision.get("id") or current.get("state") != "valid":
        return {"ok": False, "reason": "current_record_invalid_or_identity_changed"}
    if current.get("fact_type") != decision.get("actual_type"):
        return {"ok": False, "reason": "current_type_changed"}
    if sha256(str(current.get("text") or "").encode()).hexdigest() != decision.get("text_sha256"):
        return {"ok": False, "reason": "current_text_changed"}
    if decision.get("decision") == "split_required":
        return {"ok": False, "reason": "split_requires_separate_review"}
    target = {"change_to_world": "world", "change_to_experience": "experience"}.get(decision.get("decision"))
    if not target or target == current.get("fact_type"):
        return {"ok": False, "reason": "no_type_change"}
    return {"ok": True, "target_type": target}
