"""Migrate a reviewed starter view into the control registry without writing Bank content."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import urllib.parse
import urllib.request

from publisher import prepare_publication, commit_publication


def _get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=10) as response:
        return json.loads(response.read())


def migrate_starter_view(repo, manifest_path: str | Path, owner_token: str, api_url: str = "http://127.0.0.1:8888") -> list[dict]:
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get("schema") != 1 or manifest.get("bank") != repo.bank_id:
        raise ValueError("starter_manifest_bank_or_schema_mismatch")
    result = []
    categories = {"recommendations-for-decisions": "reasoning", "explanation-and-unfamiliar-terms": "learning",
                  "memory-as-reference": "collaboration", "regression-and-error-class-review": "delivery"}
    for entry in manifest.get("entries", []):
        refs = []
        for source in entry.get("sources", []):
            memory_id = source["memory_id"]
            memory = _get(api_url, "/v1/default/banks/" + urllib.parse.quote(repo.bank_id, safe="") + "/memories/" + memory_id)
            if memory.get("id") != memory_id or memory.get("state") != "valid":
                raise ValueError("starter_source_invalid:" + memory_id)
            chunk = _get(api_url, "/v1/default/chunks/" + urllib.parse.quote(source["chunk_id"], safe=""))
            text = chunk.get("chunk_text") or ""
            if chunk.get("bank_id") != repo.bank_id or chunk.get("document_id") != source["document_id"] or sha256(text.encode()).hexdigest() != source["source_sha256"]:
                raise ValueError("starter_source_revision_changed:" + memory_id)
            start = text.find(source["quote"])
            if start < 0:
                raise ValueError("starter_quote_not_found:" + memory_id)
            refs.append({"bank_id": repo.bank_id, "memory_id": memory_id, "document_id": source["document_id"], "chunk_id": source["chunk_id"],
                         "source_revision": memory.get("updated_at") or memory.get("mentioned_at") or source["source_sha256"], "source_sha256": source["source_sha256"],
                         "span_start": start, "span_end": start + len(source["quote"]), "quote": source["quote"], "stored_role": "user",
                         "origin": "user_direct", "statement_kind": "request", "event_at": memory.get("mentioned_at"),
                         "stored_at": memory.get("updated_at") or "unknown", "human_author_verified": False,
                         "origin_witness_ref": "profile-review:" + entry["id"], "origin_witness_sha256": sha256(text.encode()).hexdigest()})
        nature = "explicit_requirement" if entry.get("classification") == "scoped_requirement" else "declared_preference"
        proposal = {"proposal_id": "starter:" + entry["id"], "operation": "create", "target_id": "starter:" + entry["id"], "base_revision": repo.active_revision(),
                    "nature": nature, "primary_category": categories.get(entry["id"], "collaboration"), "related_categories": [], "text": entry["text"],
                    "applies_when": [entry["scope"]], "exceptions": ["当前用户 Prompt 或当前权威材料另有要求时优先"],
                    "effect_on_action": "在匹配范围内作为可回读参考，不扩张执行授权", "scope": {"user_id": "user", "agent_roles": [], "project_ids": [], "task_ids": [], "domains": [], "media": []},
                    "evidence_refs": refs, "source_family_ids": ["starter:" + entry["id"]]}
        review = {"support": "supported", "scope_ok": True, "conditions_preserved": True, "source_role_ok": True, "hypothetical_only": False, "conflicts": [],
                  "source_witness_hash": refs[0]["origin_witness_sha256"], "reviewer_model": manifest.get("reviewer", "starter-review"), "reviewed_at": manifest.get("reviewed_at", "unknown")}
        prepared = prepare_publication(repo, proposal, review, owner_token)
        result.append(commit_publication(repo, prepared["publication_id"], repo.active_revision(), prepared["source_tokens"], owner_token))
    return result
