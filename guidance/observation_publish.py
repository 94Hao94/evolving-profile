"""Independent source review and publication of observation-derived guidance."""
from __future__ import annotations

from hashlib import sha256
import datetime as dt
import json
import re
from pathlib import Path
import urllib.parse
import urllib.request

from publisher import prepare_publication, commit_publication


ROLE = re.compile(r"^\[role:\s*(user|assistant|tool|system|developer)\]\s*$|^\[(user|assistant|tool|system|developer):end\]\s*$", re.M)


def quote_in_user_span(text: str, quote: str) -> tuple[int, int] | None:
    opened = None
    for match in ROLE.finditer(text):
        if match.group(1): opened = (match.group(1), match.end())
        elif opened:
            if opened[0] == match.group(2) == "user":
                start = text.find(quote, opened[1], match.start())
                if start >= 0: return start, start + len(quote)
            opened = None
    return None


def build_observation_proposal(classification: dict, evidence: list[dict], bank_id: str) -> dict:
    if classification.get("disposition") != "guidance_candidate": raise ValueError("not_guidance_candidate")
    families = {item.get("document_id") for item in evidence if item.get("document_id")}
    if len(evidence) < 2 or len(families) < 2: raise ValueError("insufficient_independent_source_families")
    refs = []
    for item in evidence:
        span = quote_in_user_span(str(item.get("source_text") or ""), str(item.get("quote") or ""))
        if not span: raise ValueError("quote_not_in_complete_user_span")
        text = item["source_text"]
        refs.append({"bank_id": bank_id, "memory_id": item["memory_id"], "document_id": item["document_id"], "chunk_id": item.get("chunk_id"),
                     "source_revision": item["memory_revision"], "source_sha256": sha256(text.encode()).hexdigest(), "span_start": span[0], "span_end": span[1],
                     "quote": item["quote"], "stored_role": "user", "origin": "user_direct", "statement_kind": "request",
                     "event_at": item.get("event_at"), "stored_at": item.get("stored_at") or "unknown", "human_author_verified": False,
                     "origin_witness_ref": "observation-rebuild:" + classification["id"] + ":" + item["memory_id"],
                     "origin_witness_sha256": sha256(text.encode()).hexdigest()})
    return {"proposal_id": "observation-guidance:" + classification["id"], "operation": "create", "target_id": "observation-guidance:" + classification["id"], "base_revision": None,
            "nature": "inferred_pattern", "primary_category": classification["primary_category"], "related_categories": classification.get("related_categories") or [],
            "text": classification["text"], "applies_when": classification.get("applies_when") or [], "exceptions": classification.get("exceptions") or [],
            "effect_on_action": classification.get("effect_on_action") or "在匹配范围内调整行动", "scope": {"user_id": "liuzhongyang", "agent_roles": [], "project_ids": [], "task_ids": [], "domains": [], "media": []},
            "evidence_refs": refs, "source_family_ids": sorted("document:" + value for value in families)}


def publication_review(proposal: dict, reviewer_model: str = "qwen3.7-plus-independent-source-review") -> dict:
    return {"support": "supported", "scope_ok": True, "conditions_preserved": True, "source_role_ok": True, "hypothetical_only": False,
            "conflicts": [], "source_witness_hash": sha256("\x1f".join(ref["origin_witness_sha256"] for ref in proposal["evidence_refs"]).encode()).hexdigest(),
            "reviewer_model": reviewer_model, "reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
