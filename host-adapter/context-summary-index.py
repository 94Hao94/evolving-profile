#!/usr/bin/env python3
"""Import native Codex rollout summaries into the EP Context sidecar."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.context_summary import build_index_from_codex_memory, write_context_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-root", default=os.path.expanduser("~/.codex/memories"))
    parser.add_argument("--index", default=os.path.expanduser("~/.evolving-profile/context/context-index.json"))
    args = parser.parse_args()
    sessions, projects = build_index_from_codex_memory(args.memory_root)
    receipt = write_context_index(args.index, sessions, projects)
    receipt.update({"source": "codex_rollout_summaries", "status": "seeded_pending_review"})
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
