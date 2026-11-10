#!/usr/bin/env python3
"""Compare source, runtime and active-release files that carry host behavior."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


KEY_FILES = (
    "host-adapter/evolving_profile_controller_mcp.py",
    "host-adapter/recall.py",
    "host-adapter/lib/retention_policy.py",
    "host-adapter/lib/retention_queue.py",
    "host-adapter/lib/personal_records.py",
    "ham-os/ham/adapter.py",
    "ham-os/ham/api.py",
    "guidance/bank_hierarchy.py",
    "guidance/guidance_worker.py",
    "guidance/host_contract.py",
    "guidance/topic_catalog_worker.py",
)


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for relative in KEY_FILES:
        source = digest(args.source_root / relative)
        runtime = digest(args.runtime_root / relative)
        release = digest(args.release_root / relative)
        rows.append(
            {
                "path": relative,
                "source_sha256": source,
                "runtime_sha256": runtime,
                "release_sha256": release,
                "source_runtime_match": source is not None and source == runtime,
                "source_release_match": source is not None and source == release,
            }
        )

    result = {
        "schema": "ep.runtime-sync-audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(args.source_root),
        "runtime_root": str(args.runtime_root),
        "release_root": str(args.release_root),
        "status": "matched" if all(r["source_runtime_match"] and r["source_release_match"] for r in rows) else "drift",
        "files": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    args.output.chmod(0o600)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

