"""Apply reviewed observation dispositions transactionally and reversibly."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import asyncpg

from observation_rebuild import atomic

BANK = "personal-memory"
INSTANCE = Path.home() / ".pg0/instances/hindsight-embed-agentmemory/instance.json"


async def main(disposition_path: str, output_dir: str):
    report = json.loads(Path(disposition_path).read_text())
    if report.get("status") != "completed" or report.get("total") != report.get("completed") or report.get("failed"):
        raise ValueError("observation_dispositions_not_complete")
    decisions = {row["id"]: row for row in report["results"]}
    cfg = json.loads(INSTANCE.read_text()); root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    conn = await asyncpg.connect(user=cfg["username"], password=cfg["password"], database=cfg["database"], host="127.0.0.1", port=cfg["port"])
    try:
        rows = await conn.fetch("SELECT id::text,text,fact_type,metadata FROM memory_units WHERE bank_id=$1 AND fact_type='observation'", BANK)
        if set(decisions) != {row["id"] for row in rows}: raise ValueError("observation_set_changed_before_apply")
        meta=lambda value:json.loads(value) if isinstance(value,str) else dict(value or {})
        backup = [{"id": row["id"], "text": row["text"], "fact_type": row["fact_type"], "metadata": meta(row["metadata"])} for row in rows]
        atomic(root / "before-observations.json", {"bank": BANK, "at": dt.datetime.now(dt.timezone.utc).isoformat(), "items": backup})
        counts = {}
        async with conn.transaction():
            for row in rows:
                decision = decisions[row["id"]]; disposition = decision["disposition"]; metadata = meta(row["metadata"])
                metadata.update(guidance_v1_disposition=disposition, guidance_v1_reviewed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                                guidance_v1_category=decision.get("primary_category"), guidance_v1_reason=decision.get("reason"),
                                guidance_v1_source_family_ids=decision.get("source_family_ids") or [])
                target = "world" if disposition == "downgrade_world" else "experience" if disposition == "downgrade_experience" else "observation"
                await conn.execute("UPDATE memory_units SET metadata=$1::jsonb,fact_type=$2,updated_at=now() WHERE bank_id=$3 AND id=$4::uuid AND fact_type='observation'",
                                   json.dumps(metadata, ensure_ascii=False), target, BANK, row["id"])
                counts[disposition] = counts.get(disposition, 0) + 1
        readback = await conn.fetch("SELECT id::text,fact_type,metadata->>'guidance_v1_disposition' AS disposition FROM memory_units WHERE bank_id=$1 AND id=ANY($2::uuid[])", BANK, list(decisions))
        expected_type=lambda disposition:'world' if disposition=='downgrade_world' else 'experience' if disposition=='downgrade_experience' else 'observation'
        mismatches = [row["id"] for row in readback if row["disposition"] != decisions[row["id"]]["disposition"] or row['fact_type']!=expected_type(decisions[row['id']]['disposition'])]
        if mismatches: raise ValueError("observation_apply_readback_mismatch")
        result = {"schema": "guidance.observation-apply.v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(), "total": len(rows),
                  "counts": counts, "reclassified_world":sum(row["fact_type"]=="world" for row in readback),"reclassified_experience":sum(row["fact_type"]=="experience" for row in readback), "readback_mismatches": mismatches,
                  "rollback_source": str(root / "before-observations.json")}
        atomic(root / "apply-report.json", result); print(json.dumps(result, ensure_ascii=False))
    finally: await conn.close()


if __name__ == "__main__":
    import asyncio, sys
    asyncio.run(main(*sys.argv[1:]))
