#!/usr/bin/env python3
"""Compatibility shim (2026-10-24). Claude Code CLI hooks configured to run hook_bridge.py now run the unified, host-aware bridge
(hook_bridge_desktop.py). Fixes for the old bridge: tool_result blocks (file dumps) no longer stored as 'user' speech,
standard hookSpecificOutput format, correct agent env var, host tag (claude-cli / claude-desktop / claude-code), PreToolUse/PreCompact support.
Previous version: hook_bridge.py.pre-hostaware-<ts>. Never blocks Claude: always exit 0."""
import runpy, sys
from pathlib import Path

try:
    runpy.run_path(str(Path(__file__).resolve().with_name('hook_bridge_desktop.py')), run_name='__main__')
except SystemExit:
    raise
except BaseException as exc:  # memory degradation must never block Claude
    print(f'[Evolving Profile Claude bridge shim] {type(exc).__name__}: {str(exc)[:200]}', file=sys.stderr)
    sys.exit(0)
