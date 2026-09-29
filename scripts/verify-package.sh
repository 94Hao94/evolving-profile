#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
test -f "$ROOT/VERSION"
test -f "$ROOT/README.md"
test -f "$ROOT/.env.example"
test -d "$ROOT/guidance"
test -d "$ROOT/host-adapter"
test -d "$ROOT/console"
python3 "$ROOT/scripts/release-preflight.py" --root "$ROOT"
"$ROOT/scripts/check-no-secrets.sh"
python3 -m py_compile "$ROOT/host-adapter/guidance_entry.py" "$ROOT/host-adapter/evolving_profile_controller_mcp.py"
echo "EP $(cat "$ROOT/VERSION") package structural verification passed"
