"""Map raw thread-history candidate families back to Hindsight source witnesses."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path
import re
import sys

INSTANCE = Path.home() / ".pg0/instances/hindsight-embed-agentmemory/instance.json"
BANK = "personal-memory"


def user_spans(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"\[role:\s*user\]\s*(.*?)\s*\[user:end\]", text or "", re.S | re.I)]


async def witness(families: list[dict]) -> list[dict]:
    import asyncpg
    cfg = json.loads(INSTANCE.read_text()); db = await asyncpg.connect(user=cfg["username"], password=cfg["password"], host="127.0.0.1", port=cfg["port"], database=cfg["database"])
    result = []
    try:
        for family in families:
            quote = str(family.get("verbatim_quotes", [family.get("canonical_text", "")])[0])
            # Exact quote is authoritative. For very long messages, use a stable
            # prefix and verify the complete quote in the returned document.
            needle = quote[:900]
            rows = await db.fetch("SELECT id,created_at,original_text,tags FROM documents WHERE bank_id=$1 AND original_text LIKE $2 ORDER BY created_at DESC LIMIT 20", BANK, "%" + needle.replace("%", "") + "%")
            sources = []
            for row in rows:
                spans = user_spans(row["original_text"] or "")
                matches = [(span.find(quote), span) for span in spans if quote in span]
                if not matches:
                    continue
                memories = await db.fetch("SELECT id,text,mentioned_at,updated_at,document_id,chunk_id,fact_type FROM memory_units WHERE bank_id=$1 AND document_id=$2 ORDER BY mentioned_at NULLS LAST LIMIT 20", BANK, row["id"])
                selected = []
                for memory in memories:
                    if memory["text"] and any(memory["text"] in span or span in memory["text"] for _, span in matches):
                        selected.append({key: memory[key] for key in ("id", "text", "mentioned_at", "updated_at", "document_id", "chunk_id", "fact_type")})
                sources.append({"document_id": row["id"], "created_at": row["created_at"].isoformat(), "tags": row["tags"] or [], "user_span": matches[0][1], "memory_units": selected})
            result.append({**family, "source_witnesses": sources, "witness_document_count": len(sources), "witness_memory_count": sum(len(s["memory_units"]) for s in sources)})
    finally:
        await db.close()
    return result


async def main(input_path: str, output_path: str):
    source = json.loads(Path(input_path).read_text()); families = [row for row in source.get("items", []) if row.get("disposition") != "held"]
    rows = await witness(families)
    report = {"schema": "guidance.raw-source-witness.v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(), "source": str(input_path),
              "families": len(rows), "with_two_documents": sum(row["witness_document_count"] >= 2 for row in rows),
              "with_memory_witness": sum(row["witness_memory_count"] > 0 for row in rows), "items": rows,
              "boundary": "Source mapping only; no publication or registry mutation."}
    Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2)); print(json.dumps({k: report[k] for k in ("families", "with_two_documents", "with_memory_witness")}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
