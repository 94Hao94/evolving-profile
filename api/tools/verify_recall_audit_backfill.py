#!/usr/bin/env python3
"""Read-only verification for legacy recall-trace backfill manifests."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

import asyncpg

from evolving_profile_api.engine.audit_trace_archive import RecallTraceArchive, canonical_trace_bytes


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, required=True, help="Exact maximum manifests to verify; required for bounded reads.")
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=Path.home() / ".evolving-profile" / "audit" / "recall-trace-archive",
    )
    return parser.parse_args()


async def run(args):
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    database_url = os.environ.get("EVOLVING_PROFILE_API_DATABASE_URL")
    if not database_url:
        raise RuntimeError("EVOLVING_PROFILE_API_DATABASE_URL is required")
    manifest_root = args.archive_root / "legacy-backfill-manifests"
    paths = sorted(manifest_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[: args.limit]
    archive = RecallTraceArchive(args.archive_root)
    conn = await asyncpg.connect(database_url)
    checked = 0
    try:
        for path in paths:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest.get("status") != "archived":
                raise RuntimeError(f"manifest {path.name} is not archived")
            raw = await conn.fetchval("SELECT response->'trace' FROM public.audit_log WHERE id=$1::uuid", manifest["audit_id"])
            if raw is None:
                raise RuntimeError(f"audit row {manifest['audit_id']} lacks its original hot trace")
            hot_trace = json.loads(raw) if isinstance(raw, str) else dict(raw)
            cold_trace = archive.read_trace(manifest["trace_archive"])
            if canonical_trace_bytes(hot_trace) != canonical_trace_bytes(cold_trace):
                raise RuntimeError(f"trace mismatch for audit row {manifest['audit_id']}")
            if hashlib.sha256(canonical_trace_bytes(cold_trace)).hexdigest() != manifest["trace_archive"]["sha256"]:
                raise RuntimeError(f"cold hash mismatch for audit row {manifest['audit_id']}")
            checked += 1
    finally:
        await conn.close()
    return {"status": "verified", "checked": checked, "database_mutations": 0}


def main():
    print(json.dumps(asyncio.run(run(parse_args())), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
