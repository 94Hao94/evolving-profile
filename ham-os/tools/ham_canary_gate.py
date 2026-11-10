#!/usr/bin/env python3
"""Evaluate the user-authorized interim Phase-6 release gate.

This tool is evidence-only: it never changes production flags.  The original
255-case benchmark remains the target for the full research benchmark, while
the interim release gate is deliberately limited to the sealed evidence that
actually exists today.
"""
from __future__ import annotations

import json
from pathlib import Path


REQUIRED_LIVE_URLS = {
    "http://127.0.0.1:8879/health",
    "http://127.0.0.1:8888/health",
    "http://127.0.0.1:9998/api/status",
}
MINIMUM_SEALED_CASES = 10
FULL_BENCHMARK_CASES = 255


def load(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def live_end_to_end_passed(records: list[dict]) -> bool:
    statuses = {str(record.get("url")): record.get("status") for record in records}
    return all(statuses.get(url) == 200 for url in REQUIRED_LIVE_URLS)


def evaluate_gate(*, hidden: dict, isolation: dict, restore: dict, live_e2e: list[dict]) -> dict:
    """Return a transparent interim-release decision from immutable evidence."""
    total = int(hidden.get("total") or 0)
    passed = int(hidden.get("passed") or 0)
    gates = {
        "sealed_hidden_minimum": (
            total >= MINIMUM_SEALED_CASES
            and passed == total
            and hidden.get("overall_pass") is True
        ),
        "abc_isolation": (
            isolation.get("pollution_free") is True
            and int(isolation.get("repetitions") or 0) >= 3
        ),
        "restore_drill": (
            restore.get("status") == "passed"
            and restore.get("production_routing_changed") is False
        ),
        "live_end_to_end": live_end_to_end_passed(live_e2e),
    }
    return {
        "schema": "ham.phase6.release_gate.v2",
        "authorization": "SCR-0009-user-authorized-interim-release-gate",
        "gates": gates,
        "eligible": all(gates.values()),
        "scope": "Hindsight Controller v5 and HAM-OS shadow interim acceptance; the official Hindsight read/store path remains production",
        "benchmark_debt": {
            "target_cases": FULL_BENCHMARK_CASES,
            "sealed_cases": total,
            "remaining_cases": max(0, FULL_BENCHMARK_CASES - total),
            "status": "deferred_not_waived",
        },
        "proposed_sequence": [
            "approve the active Codex → Controller → official Hindsight production path",
            "retain HAM-OS projection as shadow evidence and retain rollback",
            "continue collecting independently sealed benchmark evidence",
        ],
        "runtime_changed": False,
    }


def main() -> int:
    root = Path("/Users/example/Documents/Codex/2026-07-11/ag/hindsight-memory-os")
    home = Path.home()
    result = evaluate_gate(
        hidden=load(home / ".hindsight/audits/hidden-recall-benchmark-latest.json"),
        isolation=load(root / "evidence/phase6-final-isolation-smoke.json"),
        restore=load(root / "evidence/phase5-system-restore-drill.json"),
        live_e2e=load(root / "evidence/phase6-interim-live-e2e.json"),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
