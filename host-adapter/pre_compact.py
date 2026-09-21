#!/usr/bin/env python3
"""PreCompact hook: save a deterministic recovery checkpoint locally."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.runtime_paths import ham_source_root

HAM_SOURCE_ROOT = ham_source_root(__file__)
if HAM_SOURCE_ROOT not in sys.path:
    sys.path.insert(0, HAM_SOURCE_ROOT)
try:
    from ham.adapter import emit as ham_emit
except Exception:
    def ham_emit(*_args, **_kwargs):
        return {"attempted": False, "reason": "adapter_unavailable"}

from lib.midtask import render_checkpoint


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return
    ham_emit("PreCompact", hook_input, "ambient_context", "checkpoint", "")
    # Codex PreCompact cannot inject additionalContext. The next compact/resume
    # SessionStart reads this durable checkpoint and performs the recovery.
    render_checkpoint(str(hook_input.get("session_id") or "unknown"), hook_input.get("cwd") or "unknown")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
