#!/usr/bin/env python3
"""Fail-closed release gate for EP source/runtime/release parity."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run_json(command: list[str]) -> dict:
    process = subprocess.run(command, text=True, capture_output=True, check=False)
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gate_tool_invalid_json:{command[0]}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"gate_tool_invalid_object:{command[0]}")
    value["exit_code"] = process.returncode
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sync = run_json(
        [
            sys.executable,
            str(args.source_root / "host-adapter/tools/runtime_sync_audit.py"),
            "--source-root",
            str(args.source_root),
            "--runtime-root",
            str(args.runtime_root),
            "--release-root",
            str(args.release_root),
            "--output",
            str(args.output.with_name("runtime-sync-audit.json")),
        ]
    )
    source_truth = run_json(
        [
            sys.executable,
            str(args.runtime_root / "host-adapter/source_of_truth_audit.py"),
            "--json",
        ]
    )
    result = {
        "schema": "ep.release-gate.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if sync.get("status") == "matched" and source_truth.get("ok") else "blocked",
        "checks": {
            "runtime_sync": sync.get("status"),
            "source_of_truth": source_truth.get("ok"),
            "source_of_truth_checks": source_truth.get("checks", []),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    args.output.chmod(0o600)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

