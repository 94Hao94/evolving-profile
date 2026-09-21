"""Discover recent raw user guidance signals before observation consolidation.

This is an inventory and candidate-generation stage. It never publishes by
itself: source-role checks, nature-specific evidence thresholds and the normal
Guidance publication gate remain downstream.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Iterable



BANK = "personal-memory"
INSTANCE = Path.home() / ".pg0/instances/hindsight-embed-agentmemory/instance.json"
ROLE_BLOCK = re.compile(r"\[role:\s*user\]\s*(.*?)\s*\[user:end\]", re.S | re.I)
SIGNAL = re.compile(r"(?:必须|一定要|以后|不要|不能|禁止|要求|偏好|喜欢|优先|记住|每次|务必|严禁|只要|除非|不再|先.+再)")
NOISE = re.compile(r"^(?:好的|好|嗯|继续|收到|谢谢|ok|OK|是的|对|明白)[。！!，, ]*$", re.I)


def extract_user_spans(text: str) -> list[str]:
    return [match.group(1).strip() for match in ROLE_BLOCK.finditer(str(text or "")) if match.group(1).strip()]


def high_signal(text: str) -> bool:
    value = re.sub(r"\s+", "", str(text or ""))
    return bool(value and len(value) >= 8 and not NOISE.match(value) and SIGNAL.search(value))


def normalize_sentence(text: str) -> str:
    value = re.sub(r"\s+", "", str(text or "")).strip("。！？!?,，；; ")
    value = re.sub(r"(?:今天|刚才|这次|本次|当前|现在)", "<context>", value)
    return value.casefold()


def cluster_events(events: Iterable[dict]) -> list[dict]:
    groups = defaultdict(list)
    for event in events:
        normalized = normalize_sentence(event.get("text", ""))
        if normalized and high_signal(event.get("text", "")):
            groups[normalized].append({**event, "normalized": normalized})
    result = []
    for normalized, rows in groups.items():
        first = rows[0]
        result.append({
            "normalized": normalized,
            "text": first["text"],
            "event_family_size": len(rows),
            "document_ids": sorted({row["document_id"] for row in rows}),
            "events": rows,
        })
    return sorted(result, key=lambda row: (-row["event_family_size"], row["normalized"]))


async def discover(days: int = 31, output: str | Path = "recent-guidance-discovery.json") -> dict:
    import asyncpg
    cfg = json.loads(INSTANCE.read_text(encoding="utf-8"))
    conn = await asyncpg.connect(user=cfg["username"], password=cfg["password"], database=cfg["database"], host="127.0.0.1", port=cfg["port"])
    try:
        rows = await conn.fetch("SELECT id,created_at,original_text,tags FROM documents WHERE bank_id=$1 AND created_at >= now()-make_interval(days=>$2::int) ORDER BY created_at DESC", BANK, days)
    finally:
        await conn.close()
    events = []
    user_documents = 0
    for row in rows:
        spans = extract_user_spans(row["original_text"] or "")
        if spans:
            user_documents += 1
        for index, span in enumerate(spans):
            if high_signal(span):
                events.append({"document_id": row["id"], "memory_id": None, "created_at": row["created_at"].isoformat(), "span_index": index, "text": span, "tags": row["tags"] or []})
    families = cluster_events(events)
    report = {
        "schema": "guidance.recent-user-guidance-discovery.v1",
        "bank_id": BANK,
        "days": days,
        "documents_scanned": len(rows),
        "documents_with_user_spans": user_documents,
        "high_signal_user_spans": len(events),
        "event_families": len(families),
        "family_size_distribution": {str(size): sum(1 for family in families if family["event_family_size"] == size) for size in sorted({family["event_family_size"] for family in families})},
        "families": families,
        "publication_boundary": "inventory_only; requires nature classification, source witness and normal controlled publication",
    }
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=31)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(discover(args.days, args.output)), ensure_ascii=False))
