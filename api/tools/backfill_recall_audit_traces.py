#!/usr/bin/env python3
"""Copy legacy recall audit traces into cold storage without changing PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import asyncpg

from evolving_profile_api.engine.audit_trace_archive import RecallTraceArchive
from evolving_profile_api.engine.audit_trace_backfill import backfill_trace


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, required=True, help="Exact maximum number of rows to copy; required for safety.")
    parser.add_argument("--bank-id", help="Optional Bank restriction.")
    parser.add_argument("--order", choices=("largest", "oldest"), default="largest")
    parser.add_argument("--dry-run", action="store_true", help="Report candidates without writing archive objects or manifests.")
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=Path.home() / ".evolving-profile" / "audit" / "recall-trace-archive",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict[str, object]:
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    database_url = os.environ.get("EVOLVING_PROFILE_API_DATABASE_URL")
    if not database_url:
        raise RuntimeError("EVOLVING_PROFILE_API_DATABASE_URL is required")
    where = "action = 'recall' AND jsonb_typeof(response->'trace') = 'object'"
    values: list[object] = []
    if args.bank_id:
        values.append(args.bank_id)
        where += f" AND bank_id = ${len(values)}"
    values.append(args.limit)
    order = "pg_column_size(response) DESC" if args.order == "largest" else "started_at ASC"
    sql = f"SELECT id::text AS id, response FROM public.audit_log WHERE {where} ORDER BY {order} LIMIT ${len(values)}"

    conn = await asyncpg.connect(database_url)
    try:
        rows = await conn.fetch(sql, *values)
    finally:
        await conn.close()

    archive = RecallTraceArchive(args.archive_root)
    manifest_root = args.archive_root / "legacy-backfill-manifests"
    archived = 0
    skipped = 0
    for row in rows:
        response_value = row["response"]
        response = json.loads(response_value) if isinstance(response_value, str) else dict(response_value)
        if args.dry_run:
            continue
        manifest = backfill_trace(row["id"], response, archive, manifest_root)
        archived += int(manifest["status"] == "archived")
        skipped += int(manifest["status"] != "archived")
    return {
        "status": "dry-run" if args.dry_run else "completed",
        "selected": len(rows),
        "archived": archived,
        "would_archive": len(rows) if args.dry_run else 0,
        "skipped": skipped,
        "database_mutations": 0,
        "archive_root": str(args.archive_root),
    }


def main() -> None:
    print(json.dumps(asyncio.run(run(parse_args())), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
