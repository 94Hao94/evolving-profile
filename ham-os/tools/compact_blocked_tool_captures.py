#!/usr/bin/env python3
"""Archive and compact permanently blocked oversized PostToolUse captures.

Default mode is read-only. ``--apply`` updates only rows that are still
``blocked`` with the recorded 413 failure and whose original input hash matches.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from ham.capture_tool_response_compaction import compact_blocked_post_tool_event


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, required=True, help="Exact maximum candidate rows; required for safety.")
    parser.add_argument("--apply", action="store_true", help="Persist compact envelopes after archive verification.")
    parser.add_argument(
        "--capture-db", type=Path, default=Path.home() / ".evolving-profile" / "memory-os" / "capture" / "capture.sqlite3"
    )
    return parser.parse_args()


def run(args):
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    db_path = Path(args.capture_db)
    archive_root = db_path.parent
    manifests = archive_root / "tool-response-archive" / "legacy-manifests"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT capture_order, input_hash, envelope_json
            FROM captures
            WHERE status='blocked'
              AND last_error LIKE 'HTTPError:HTTP Error 413:%'
              AND json_extract(envelope_json,'$.provenance.hook')='PostToolUse'
              AND json_extract(envelope_json,'$.source_payload.tool_response') IS NOT NULL
            ORDER BY capture_order
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        compacted = 0
        bytes_before = 0
        bytes_after = 0
        for row in rows:
            original_json = row["envelope_json"]
            original = json.loads(original_json)
            bytes_before += len(original_json.encode("utf-8"))
            if not args.apply:
                continue
            compact, manifest = compact_blocked_post_tool_event(original, archive_root)
            if compact is None:
                continue
            compact_json = json.dumps(compact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            bytes_after += len(compact_json.encode("utf-8"))
            manifests.mkdir(parents=True, exist_ok=True, mode=0o700)
            manifest["capture_order"] = row["capture_order"]
            manifest["input_hash"] = row["input_hash"]
            manifest_path = manifests / f"{row['capture_order']}.json"
            temporary = manifest_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(manifest_path)
            with connection:
                changed = connection.execute(
                    """
                    UPDATE captures SET envelope_json=?
                    WHERE capture_order=? AND input_hash=? AND status='blocked'
                      AND last_error LIKE 'HTTPError:HTTP Error 413:%'
                    """,
                    (compact_json, row["capture_order"], row["input_hash"]),
                ).rowcount
            compacted += int(changed == 1)
        return {
            "status": "completed" if args.apply else "dry-run",
            "selected": len(rows),
            "compacted": compacted,
            "database_mutations": compacted,
            "estimated_bytes_before": bytes_before,
            "estimated_bytes_after": bytes_after if args.apply else None,
            "estimated_bytes_released_from_sqlite": bytes_before - bytes_after if args.apply else 0,
        }
    finally:
        connection.close()


def main():
    print(json.dumps(run(parse_args()), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
