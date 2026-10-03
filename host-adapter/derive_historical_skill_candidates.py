#!/usr/bin/env python3
"""Derive visible, non-retrievable skill hypotheses from repeated history patterns."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from lib.process_memory import ProcessMemoryStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default=str(Path.home() / ".evolving-profile/process-memory/records.json"))
    parser.add_argument("--min-patterns", type=int, default=2)
    args = parser.parse_args()
    store = ProcessMemoryStore(args.store)
    records = store.all()
    groups: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for row in records:
        if row.get("kind") != "pattern" or row.get("rollout_state") != "shadow":
            continue
        if not row.get("historical_candidate_id") and not str(row.get("process_memory_id", "")).startswith("pm_pattern_candidate_"):
            continue
        key = tuple(sorted(str(item) for item in (row.get("task_archetype") or ["other"])))
        groups[key].append(row)
    existing = {
        tuple(sorted(str(item) for item in (row.get("task_archetype") or ["other"])))
        for row in records
        if row.get("kind") == "skill" and row.get("status") == "candidate"
    }
    created = []
    for key, patterns in sorted(groups.items()):
        if len(patterns) < max(2, args.min_patterns) or key in existing:
            continue
        ids = [str(row["process_memory_id"]) for row in patterns]
        dimensions = sorted({dimension for row in patterns for dimension in row.get("process_dimensions") or []})
        label = "、".join(key)
        candidate = store.record_skill_candidate(ids, {
            "text": f"历史候选程序技能：{label}任务中重复出现的过程模式（{len(patterns)} 条模式，维度：{'、'.join(dimensions) or '过程观察'}）。需要新任务上的独立验证后才能发布。",
            "process_dimensions": dimensions,
            "source_recheck_status": "passed",
        })
        created.append(candidate["process_memory_id"])
    print(json.dumps({
        "schema": "evolving-profile.historical-skill-candidates.v1",
        "groups": {"/".join(key): len(rows) for key, rows in groups.items()},
        "created": len(created),
        "process_memory_ids": created,
        "default_retrieval": "excluded_until_verified",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
