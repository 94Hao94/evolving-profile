"""Apply reviewed world/experience type changes without touching text or embeddings."""
from __future__ import annotations

import asyncpg
import datetime as dt
import json
from pathlib import Path

from observation_rebuild import atomic
from taxonomy_apply import eligible_change

BANK = "personal-memory"
INSTANCE = Path.home() / ".pg0/instances/hindsight-embed-agentmemory/instance.json"


async def main(audit_path: str, output_dir: str):
    audit = json.loads(Path(audit_path).read_text())
    if audit.get("status") != "completed" or audit.get("failed"):
        raise ValueError("taxonomy_audit_not_complete")
    cfg = json.loads(INSTANCE.read_text()); root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    conn = await asyncpg.connect(user=cfg["username"], password=cfg["password"], database=cfg["database"], host="127.0.0.1", port=cfg["port"])
    applied, held, backup = [], [], []
    try:
        decisions = {row["id"]: row for row in audit["results"]}
        rows = await conn.fetch("SELECT id::text,text,fact_type,metadata FROM memory_units WHERE bank_id=$1 AND id=ANY($2::uuid[])", BANK, list(decisions))
        current = {row["id"]: {**dict(row),'state':'valid'} for row in rows}
        if set(current) != set(decisions): raise ValueError("taxonomy_record_set_changed")
        for memory_id, decision in decisions.items():
            eligibility = eligible_change(current[memory_id], decision)
            if eligibility["ok"]:
                value=current[memory_id]["metadata"];metadata=json.loads(value) if isinstance(value,str) else dict(value or {})
                backup.append({"id": memory_id, "fact_type": current[memory_id]["fact_type"], "metadata": metadata})
                applied.append({"id": memory_id, "from": current[memory_id]["fact_type"], "to": eligibility["target_type"], "decision": decision})
            elif decision.get("decision") != "keep": held.append({"id": memory_id, "reason": eligibility["reason"], "decision": decision})
        atomic(root / "before-taxonomy.json", {"bank": BANK, "at": dt.datetime.now(dt.timezone.utc).isoformat(), "items": backup})
        async with conn.transaction():
            for item in applied:
                value=current[item["id"]]["metadata"];metadata=json.loads(value) if isinstance(value,str) else dict(value or {}); metadata.update(guidance_v1_taxonomy_previous=item["from"], guidance_v1_taxonomy_reviewed_at=dt.datetime.now(dt.timezone.utc).isoformat(), guidance_v1_taxonomy_reason=item["decision"].get("reason"))
                await conn.execute("UPDATE memory_units SET fact_type=$1,metadata=$2::jsonb,updated_at=now() WHERE bank_id=$3 AND id=$4::uuid AND fact_type=$5",
                                   item["to"], json.dumps(metadata, ensure_ascii=False), BANK, item["id"], item["from"])
        changed = await conn.fetch("SELECT id::text,fact_type FROM memory_units WHERE bank_id=$1 AND id=ANY($2::uuid[])", BANK, [row["id"] for row in applied]) if applied else []
        got = {row["id"]: row["fact_type"] for row in changed}; mismatches = [row["id"] for row in applied if got.get(row["id"]) != row["to"]]
        if mismatches: raise ValueError("taxonomy_apply_readback_mismatch")
        result = {"schema": "guidance.taxonomy-apply.v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(), "reviewed": len(decisions), "applied": len(applied),
                  "world_to_experience": sum(row["from"] == "world" and row["to"] == "experience" for row in applied),
                  "experience_to_world": sum(row["from"] == "experience" and row["to"] == "world" for row in applied), "held": len(held), "readback_mismatches": mismatches,
                  "rollback_source": str(root / "before-taxonomy.json"), "held_items": held}
        atomic(root / "apply-report.json", result); print(json.dumps({key: result[key] for key in ("reviewed", "applied", "world_to_experience", "experience_to_world", "held", "readback_mismatches")}, ensure_ascii=False))
    finally: await conn.close()


if __name__ == "__main__":
    import asyncio, sys
    asyncio.run(main(*sys.argv[1:]))
