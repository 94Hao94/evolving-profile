#!/usr/bin/env python3
"""Scan Codex/Vision JSONL exports into a read-only EP5 candidate report."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from lib.history_bootstrap import scan_history_lines, paginate_candidates, candidate_quality_stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--cutoff", default="2026-09-30T00:00:00+08:00")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    cutoff = datetime.fromisoformat(args.cutoff).astimezone(timezone.utc)
    rows = []
    for path in args.inputs:
        rows.extend(scan_history_lines(path.read_text(encoding="utf-8", errors="replace").splitlines(), cutoff=cutoff))
    page = paginate_candidates(rows, offset=args.offset, limit=args.limit)
    payload = {"schema": "evolving-profile.historical-process-bootstrap.v1", "mode": "read_only_candidate", "cutoff": cutoff.isoformat(), "quality": candidate_quality_stats(rows), "page": page}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
