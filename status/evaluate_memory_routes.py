#!/usr/bin/env python3
"""Route-contract evaluation for Evolving Profile 2.0.

This checks deterministic routing before it is handed to Codex. It does not
write Bank memory or claim the model followed a route.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


CASES = [
    ("single-history", "请回顾上次 Evolving Profile 的改动", "recall"),
    ("timeline-conflict", "回顾之前项目的时间线、实体冲突和原始来源", "research"),
    ("exact-source", "请回读记忆 fbf6ead8-8696-4adc-8331-25f23bfbca5e 的原文出处和版本", "read_source"),
    ("self-contained", "把这段文字改成三句话", "skip"),
    ("preference", "按我平时的交付偏好说明这份方案", "recall"),
]


def main() -> int:
    source = Path(__file__).with_name("evolving_profile_status_server.py")
    spec = importlib.util.spec_from_file_location("route_eval_status", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = []
    for name, prompt, expected in CASES:
        actual = module.memory_check(prompt)
        rows.append({"id": name, "expected": expected, "actual": actual["recommended_route"], "matched_nodes": actual["matched_nodes"], "passed": actual["recommended_route"] == expected})
    result = {"schema": "evolving-profile.route-eval.v1", "cases": rows, "passed": sum(row["passed"] for row in rows), "total": len(rows)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
