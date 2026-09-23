#!/usr/bin/env python3
"""Build or advance the bounded-context sidecar for one Codex rollout."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.session_context_index import DEFAULT_INDEX_PATH, index_transcript


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Codex rollout JSONL")
    parser.add_argument("--index", default=DEFAULT_INDEX_PATH, help="SQLite sidecar path")
    parser.add_argument("--rebuild", action="store_true", help="rebuild durable index from raw source")
    parser.add_argument("--tail-bytes", type=int, default=0,
                        help="first-run live bootstrap window; omit for a full backfill")
    arguments = parser.parse_args()
    receipt = index_transcript(
        arguments.source, arguments.index, rebuild=arguments.rebuild,
        bootstrap_tail_bytes=arguments.tail_bytes or None,
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
