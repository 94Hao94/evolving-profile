#!/usr/bin/env python3
"""Partition large append-only audit JSONL files into monthly gzip archives."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


FILES = ("query-controller.jsonl", "memory-effectiveness.jsonl", "mcp-tool-activity.jsonl", "prompt-ingress.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-root", type=Path, required=True)
    parser.add_argument("--cutoff-days", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, args.cutoff_days))
    archive_root = args.audit_root / "archive"
    manifest = {
        "schema": "ep.audit-rotation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cutoff": cutoff.isoformat(),
        "files": [],
        "source_untouched_outside_target_files": True,
    }
    for name in FILES:
        source = args.audit_root / name
        if not source.exists():
            continue
        temp = source.with_suffix(source.suffix + ".rotate.tmp")
        archived = retained = 0
        archived_bytes = retained_bytes = 0
        with source.open("rb") as inp, temp.open("wb") as out:
            for raw in inp:
                target_archive = None
                try:
                    row = json.loads(raw)
                    stamp = row.get("at") or row.get("recorded_at") or row.get("timestamp") or row.get("started_at")
                    when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")) if stamp else None
                    if when and when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    if when and when < cutoff:
                        target_archive = archive_root / when.strftime("%Y-%m") / f"{name}.gz"
                except (ValueError, TypeError, json.JSONDecodeError):
                    pass
                if target_archive is None:
                    out.write(raw)
                    retained += 1
                    retained_bytes += len(raw)
                else:
                    target_archive.parent.mkdir(parents=True, exist_ok=True)
                    with gzip.open(target_archive, "ab", compresslevel=6) as gz:
                        gz.write(raw)
                    archived += 1
                    archived_bytes += len(raw)
        os.chmod(temp, 0o600)
        os.replace(temp, source)
        manifest["files"].append({"file": name, "archived_lines": archived, "archived_bytes": archived_bytes, "retained_lines": retained, "retained_bytes": retained_bytes})
    for archive in archive_root.rglob("*.gz") if archive_root.exists() else []:
        os.chmod(archive, 0o600)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    args.output.chmod(0o600)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

