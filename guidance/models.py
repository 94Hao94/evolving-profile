"""Versioned behavioral models composed only from active GuidanceUnit revisions."""
from __future__ import annotations

from repository import GuidanceRepository


class ModelPublicationError(RuntimeError):
    def __init__(self, code: str): self.code = code; super().__init__(code)


def validate_atomic_model(repo: GuidanceRepository, model: dict) -> None:
    if model.get("model_kind") != "atomic_cross_dimensional":
        return
    required = ("mechanism", "dimensions", "confidence", "last_verified_at")
    if any(model.get(key) in (None, "", []) for key in required) or model.get("status") != "active":
        raise ModelPublicationError("invalid_atomic_model_contract")
    dimensions = {str(value) for value in model.get("dimensions") or []}
    if len(dimensions) < 2:
        raise ModelPublicationError("atomic_model_requires_two_dimensions")
    active_units = {(unit["id"], unit["revision"]): unit for unit in repo.active_units()}
    refs = {
        (ref.get("id"), ref.get("revision"))
        for section in model.get("sections") or []
        for ref in section.get("guidance_refs") or []
    }
    if len(refs) < 2:
        raise ModelPublicationError("atomic_model_requires_two_references")
    referenced_dimensions = {
        str(active_units[ref].get("primary_category") or "")
        for ref in refs if ref in active_units and active_units[ref].get("primary_category")
    }
    if len(referenced_dimensions) < 2 or not dimensions.issubset(referenced_dimensions):
        raise ModelPublicationError("atomic_model_dimensions_not_supported")


def publish_model(repo: GuidanceRepository, model: dict) -> dict:
    required = ("id", "revision", "title", "purpose", "sections")
    if not isinstance(model, dict) or any(not model.get(key) for key in required) or not isinstance(model["sections"], list):
        raise ModelPublicationError("invalid_model_contract")
    active = {(unit["id"], unit["revision"]) for unit in repo.active_units()}
    section_ids = set()
    for section in model["sections"]:
        if not isinstance(section, dict) or not all(key in section for key in ("section_id", "text", "applies_when", "exceptions", "guidance_refs", "counterevidence")):
            raise ModelPublicationError("invalid_model_section")
        if section["section_id"] in section_ids: raise ModelPublicationError("duplicate_section_id")
        section_ids.add(section["section_id"])
        for ref in section["guidance_refs"]:
            if (ref.get("id"), ref.get("revision")) not in active:
                raise ModelPublicationError("inactive_guidance_reference")
    validate_atomic_model(repo, model)
    repo.store_model(model)
    return {"state": "active", "model_id": model["id"], "revision": model["revision"], "section_count": len(model["sections"])}
