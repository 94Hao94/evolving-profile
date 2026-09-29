"""Evidence-bound rollback for Multi-dimensional Preference data changes.

The default mode only builds a deterministic plan. Applying the plan requires
both ``--apply`` and the exact confirmation token, then validates every target
before changing the Hindsight database or official API objects.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
from hashlib import sha256
import json
from pathlib import Path
import urllib.parse
import urllib.request

from observation_rebuild import atomic


BANK = "personal-memory"
API = "http://127.0.0.1:8888"
RELEASED_AT = "2026-09-10T07:57:00+00:00"
CONFIRMATION = "ROLLBACK_GUIDANCE_V1_DATA"
MODEL_IDS = [
    "liuzhongyang-ai-operating-system",
    "liuzhongyang-work-project-architecture",
    "liuzhongyang-business-architecture",
    "liuzhongyang-cognition-learning",
    "liuzhongyang-collaboration-delivery",
]
INSTANCE = Path.home() / ".pg0/instances/hindsight-embed-agentmemory/instance.json"


def _read(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("rollback_evidence_missing:" + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _model_restore(history: list[dict], model_id: str) -> dict:
    candidates = []
    for row in history:
        content = row.get("previous_content")
        based_on = ((row.get("previous_reflect_response") or {}).get("based_on") or {})
        guidance_refs = based_on.get("guidance_units") or []
        if row.get("changed_at", "") >= RELEASED_AT and isinstance(content, str) and content.strip() and not guidance_refs and "来源指导：" not in content:
            candidates.append(row)
    if not candidates:
        raise ValueError("pre_guidance_model_revision_not_found:" + model_id)
    selected = min(candidates, key=lambda row: row["changed_at"])
    content = selected["previous_content"]
    return {
        "model_id": model_id,
        "content": content,
        "content_sha256": sha256(content.encode()).hexdigest(),
        "history_changed_at": selected["changed_at"],
        "based_on": ((selected.get("previous_reflect_response") or {}).get("based_on") or {}),
    }


def build_plan(evidence_root: str | Path, history_loader, model_ids: list[str] | None = None, current_memory_loader=None) -> dict:
    root = Path(evidence_root)
    observation_backup = _read(root / "20260910T091000Z-observation-apply/before-observations.json")
    observation_apply = _read(root / "20260910T091000Z-observation-apply/apply-report.json")
    dispositions = _read(root / "20260910T085000Z-observation-rebuild/observation-dispositions.json")
    taxonomy_backup = _read(root / "20260910T201000Z-taxonomy-apply/before-taxonomy.json")
    taxonomy_apply = _read(root / "20260910T201000Z-taxonomy-apply/apply-report.json")
    split_backup = _read(root / "20260910T202000Z-taxonomy-splits/before-splits.json")
    split_report = _read(root / "20260910T202000Z-taxonomy-splits/split-report.json")
    empty_resolution = _read(root / "20260910T202000Z-taxonomy-splits/empty-split-resolution.json")
    rule_audit = _read(root / "20260910T085500Z-taxonomy-audit/rule-audit.json")

    banks = {value.get("bank") for value in (observation_backup, taxonomy_backup, split_backup)}
    if len(banks) != 1 or None in banks:
        raise ValueError("rollback_bank_mismatch")
    bank_id = banks.pop()

    observation_rows = {row["id"]: row for row in observation_backup.get("items") or []}
    changed_dispositions = {
        row["id"]: row for row in dispositions.get("results") or []
        if row.get("disposition") in {"downgrade_world", "downgrade_experience"}
    }
    expected_observations = int(observation_apply.get("reclassified_world", 0)) + int(observation_apply.get("reclassified_experience", 0))
    if len(changed_dispositions) != expected_observations and current_memory_loader is not None:
        current = current_memory_loader(list(observation_rows))
        changed_dispositions = {}
        for memory_id, value in current.items():
            metadata = value.get("metadata") or {}
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            disposition = metadata.get("guidance_v1_disposition")
            if disposition in {"downgrade_world", "downgrade_experience"}:
                changed_dispositions[memory_id] = {"id": memory_id, "disposition": disposition}
    if len(changed_dispositions) != expected_observations or not set(changed_dispositions).issubset(observation_rows):
        raise ValueError("observation_backup_count_mismatch")
    observation_restores = []
    for memory_id, decision in sorted(changed_dispositions.items()):
        row = dict(observation_rows[memory_id])
        row["expected_after_type"] = "world" if decision["disposition"] == "downgrade_world" else "experience"
        observation_restores.append(row)

    taxonomy_restores = sorted(taxonomy_backup.get("items") or [], key=lambda row: row["id"])
    if len(taxonomy_restores) != int(taxonomy_apply.get("applied", -1)):
        raise ValueError("taxonomy_backup_count_mismatch")

    split_restores = sorted(split_backup.get("items") or [], key=lambda row: row["row"]["id"])
    if len(split_restores) != int(split_report.get("split", -1)):
        raise ValueError("split_backup_count_mismatch")
    new_ids = [row.get("new_id") for row in split_restores]
    if None in new_ids or len(set(new_ids)) != len(new_ids):
        raise ValueError("split_new_id_mismatch")

    held_ids = {row.get("id") for row in split_report.get("held_items") or []}
    if len(held_ids) != int(split_report.get("held", -1)):
        raise ValueError("empty_split_denominator_mismatch")
    resolution_rows = {row["id"]: row for row in empty_resolution.get("items") or []}
    if set(resolution_rows) != held_ids or empty_resolution.get("failed") or empty_resolution.get("held"):
        raise ValueError("empty_split_resolution_incomplete")
    original_rows = {
        row["id"]: row for row in _objects(rule_audit)
        if row.get("id") in held_ids and row.get("actual_type") in {"world", "experience"} and isinstance(row.get("text"), str)
    }
    if set(original_rows) != held_ids:
        raise ValueError("empty_split_original_missing")
    covered_by_full_backup = {row["id"] for row in observation_restores} | {row["id"] for row in taxonomy_restores}
    empty_split_restores = []
    for memory_id in sorted(held_ids):
        if memory_id in covered_by_full_backup:
            continue
        original, after = original_rows[memory_id], resolution_rows[memory_id]
        empty_split_restores.append({
            "id": memory_id,
            "fact_type": original["actual_type"],
            "text": original["text"],
            "expected_after_type": after.get("to") or original["actual_type"],
            "expected_after_sha256": after.get("text_sha256"),
        })

    model_restores = [_model_restore(history_loader(model_id), model_id) for model_id in (model_ids or MODEL_IDS)]
    plan = {
        "schema": "guidance.data-rollback-plan.v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": "dry_run",
        "bank_id": bank_id,
        "observation_restores": observation_restores,
        "taxonomy_restores": taxonomy_restores,
        "split_restores": split_restores,
        "empty_split_restores": empty_split_restores,
        "model_restores": model_restores,
    }
    plan["summary"] = {
        "observation_restores": len(observation_restores),
        "taxonomy_restores": len(taxonomy_restores),
        "split_original_restores": len(split_restores),
        "split_sibling_deletes": len(split_restores),
        "empty_split_restores": len(held_ids),
        "model_restores": len(model_restores),
    }
    digest_payload = {key: value for key, value in plan.items() if key not in {"generated_at", "plan_sha256"}}
    plan["plan_sha256"] = sha256(json.dumps(digest_payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return plan


def require_confirmation(apply: bool, confirmation: str | None) -> str:
    if not apply:
        return "dry_run"
    if confirmation != CONFIRMATION:
        raise PermissionError("rollback_confirmation_required")
    return "apply"


def _api_get(path: str) -> dict | list:
    with urllib.request.urlopen(API + path, timeout=30) as response:
        return json.loads(response.read())


def _api_patch(path: str, payload: dict) -> dict:
    request = urllib.request.Request(API + path, data=json.dumps(payload, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"}, method="PATCH")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def history_loader(model_id: str) -> list[dict]:
    bank = urllib.parse.quote(BANK, safe="")
    model = urllib.parse.quote(model_id, safe="")
    return _api_get(f"/v1/default/banks/{bank}/mental-models/{model}/history")


async def _database_memory_rows(ids: list[str]) -> dict:
    import asyncpg

    cfg = json.loads(INSTANCE.read_text(encoding="utf-8"))
    db = await asyncpg.connect(user=cfg["username"], password=cfg["password"], database=cfg["database"], host="127.0.0.1", port=cfg["port"])
    try:
        rows = await db.fetch("SELECT id::text,fact_type,metadata FROM memory_units WHERE bank_id=$1 AND id=ANY($2::uuid[])", BANK, ids)
        return {row["id"]: {"fact_type": row["fact_type"], "metadata": row["metadata"]} for row in rows}
    finally:
        await db.close()


def current_memory_loader(ids: list[str]) -> dict:
    return asyncio.run(_database_memory_rows(ids))


async def _apply_database(plan: dict) -> dict:
    import asyncpg

    cfg = json.loads(INSTANCE.read_text(encoding="utf-8"))
    db = await asyncpg.connect(user=cfg["username"], password=cfg["password"], database=cfg["database"], host="127.0.0.1", port=cfg["port"])
    counts = {"taxonomy": 0, "splits": 0, "observations": 0}
    try:
        async with db.transaction():
            for item in plan["taxonomy_restores"]:
                current = await db.fetchrow("SELECT fact_type FROM memory_units WHERE bank_id=$1 AND id=$2::uuid", plan["bank_id"], item["id"])
                if not current:
                    raise ValueError("rollback_target_missing:" + item["id"])
                if current["fact_type"] != item["fact_type"]:
                    await db.execute("UPDATE memory_units SET fact_type=$1,metadata=$2::jsonb,updated_at=now() WHERE bank_id=$3 AND id=$4::uuid", item["fact_type"], json.dumps(item.get("metadata") or {}, ensure_ascii=False), plan["bank_id"], item["id"])
                    counts["taxonomy"] += 1
            for item in plan["split_restores"]:
                row, new_id = item["row"], item["new_id"]
                sibling = await db.fetchrow("SELECT metadata FROM memory_units WHERE bank_id=$1 AND id=$2::uuid", plan["bank_id"], new_id)
                if not sibling:
                    raise ValueError("split_sibling_missing:" + new_id)
                sibling_meta = sibling["metadata"] if isinstance(sibling["metadata"], dict) else json.loads(sibling["metadata"] or "{}")
                if sibling_meta.get("guidance_v1_split_source_id") != row["id"]:
                    raise ValueError("split_sibling_identity_mismatch:" + new_id)
                await db.execute("DELETE FROM unit_entities WHERE unit_id=$1::uuid", new_id)
                await db.execute("DELETE FROM memory_units WHERE bank_id=$1 AND id=$2::uuid", plan["bank_id"], new_id)
                await db.execute(
                    "UPDATE memory_units SET text=$1,embedding=$2::vector,context=$3,event_date=$4::timestamptz,occurred_start=$5::timestamptz,occurred_end=$6::timestamptz,mentioned_at=$7::timestamptz,fact_type=$8,metadata=$9::jsonb,chunk_id=$10,tags=$11::text[],proof_count=$12,source_memory_ids=$13::uuid[],consolidated_at=$14::timestamptz,observation_scopes=$15::jsonb,text_signals=$16,search_vector=to_tsvector('simple',$1),search_vector_cjk_v1=NULL,consolidation_failed_at=$17::timestamptz,edited_at=$18::timestamptz,updated_at=now() WHERE bank_id=$19 AND id=$20::uuid",
                    row["text"], row.get("embedding"), row.get("context"), row.get("event_date"), row.get("occurred_start"), row.get("occurred_end"), row.get("mentioned_at"), row["fact_type"], json.dumps(row.get("metadata") or {}, ensure_ascii=False) if not isinstance(row.get("metadata"), str) else row["metadata"], row.get("chunk_id"), row.get("tags") or [], row.get("proof_count") or 0, row.get("source_memory_ids") or [], row.get("consolidated_at"), row.get("observation_scopes"), row.get("text_signals"), row.get("consolidation_failed_at"), row.get("edited_at"), plan["bank_id"], row["id"],
                )
                counts["splits"] += 1
            for item in plan["observation_restores"]:
                current = await db.fetchrow("SELECT fact_type FROM memory_units WHERE bank_id=$1 AND id=$2::uuid", plan["bank_id"], item["id"])
                if not current:
                    raise ValueError("rollback_target_missing:" + item["id"])
                if current["fact_type"] != item["fact_type"]:
                    await db.execute("UPDATE memory_units SET text=$1,fact_type=$2,metadata=$3::jsonb,updated_at=now() WHERE bank_id=$4 AND id=$5::uuid", item["text"], item["fact_type"], json.dumps(item.get("metadata") or {}, ensure_ascii=False), plan["bank_id"], item["id"])
                    counts["observations"] += 1
        return counts
    finally:
        await db.close()


def apply_plan(plan: dict, confirmation: str) -> dict:
    require_confirmation(True, confirmation)
    database = asyncio.run(_apply_database(plan))
    bank = urllib.parse.quote(plan["bank_id"], safe="")
    memory_results = []
    for item in plan["empty_split_restores"]:
        path = f"/v1/default/banks/{bank}/memories/{urllib.parse.quote(item['id'], safe='')}"
        current = _api_get(path)
        current_type = current.get("fact_type") or current.get("type")
        if current_type == item["fact_type"] and current.get("text") == item["text"]:
            memory_results.append({"id": item["id"], "state": "already_restored"})
            continue
        if current_type != item["expected_after_type"] or sha256(current.get("text", "").encode()).hexdigest() != item["expected_after_sha256"]:
            raise ValueError("empty_split_current_revision_changed:" + item["id"])
        _api_patch(path, {"text": item["text"], "fact_type": item["fact_type"]})
        memory_results.append({"id": item["id"], "state": "restored"})

    from hindsight_api.engine.candidate_revision import revision_digest

    model_results = []
    for item in plan["model_restores"]:
        path = f"/v1/default/banks/{bank}/mental-models/{urllib.parse.quote(item['model_id'], safe='')}"
        current = _api_get(path)
        if current.get("content") == item["content"]:
            model_results.append({"model_id": item["model_id"], "state": "already_restored"})
            continue
        payload = {"reviewed_candidate": {"content": item["content"], "candidate_sha256": item["content_sha256"], "base_revision_sha256": revision_digest(current), "reviewer": "guidance-v1-data-rollback", "review_note": "Restore the pre-Guidance-V1 official model revision selected from official history.", "based_on": item["based_on"]}}
        _api_patch(path, payload)
        model_results.append({"model_id": item["model_id"], "state": "restored"})
    return {"database": database, "memories": memory_results, "models": model_results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmation")
    args = parser.parse_args()
    mode = require_confirmation(args.apply, args.confirmation)
    plan = build_plan(args.evidence_root, history_loader, current_memory_loader=current_memory_loader)
    report = dict(plan)
    report["mode"] = mode
    if mode == "apply":
        report["apply_result"] = apply_plan(plan, args.confirmation)
    atomic(Path(args.output), report)
    print(json.dumps({"mode": mode, "summary": plan["summary"], "plan_sha256": plan["plan_sha256"], "output": args.output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
