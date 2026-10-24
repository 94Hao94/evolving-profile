#!/bin/zsh
# Install / uninstall the EP hook plugin for Claude Desktop (Cowork sessions).
# sudo is needed ONLY to write /Library/Application Support/Claude/org-plugins/ (Claude Desktop's documented system-wide plugin dir).
# Touches nothing under ~/.codex, ~/.claude or claude_desktop_config.json.
#   install  : zsh install-desktop-plugin.sh
#   uninstall: zsh install-desktop-plugin.sh --uninstall
set -e
HERE=${0:A:h}
EP_HOME=${EP_HOME:-$HOME/.evolving-profile}
SRC=$HERE/desktop-plugin/ep-desktop-bridge
ROOT="/Library/Application Support/Claude/org-plugins"
DEST="$ROOT/ep-desktop-bridge"
PY=$EP_HOME/runtime/python-3.11/bin/python; [[ -x $PY ]] || PY=$(command -v python3)
BR=$EP_HOME/claude-code/hook_bridge_desktop.py

if [[ "$1" == "--uninstall" ]]; then
  echo "Removing $DEST (Claude Desktop unregisters it at next launch)"; sudo rm -rf "$DEST"
  echo "done. Quit (Cmd+Q) and reopen Claude Desktop."; exit 0
fi

[[ -f "$SRC/.claude-plugin/plugin.json" && -f "$SRC/hooks/hooks.json" ]] || { echo "ABORT: plugin template missing at $SRC"; exit 1; }
[[ -f "$BR" ]] || { echo "ABORT: $BR missing - run install.sh first"; exit 1; }
"$PY" -m py_compile "$BR" && echo "[1] bridge compiles"
echo "[2] EP health: $(curl -s --noproxy '*' -m 5 http://127.0.0.1:12079/health | head -c 120)"

STAGE=$(mktemp -d /private/tmp/ep_plugin.XXXXXX); trap 'rm -rf "$STAGE"' EXIT
cp -R "$SRC" "$STAGE/ep-desktop-bridge"
"$PY" - "$STAGE/ep-desktop-bridge/hooks/hooks.json" "$PY" "$BR" <<'EOF'
import json, sys
p, py, br = sys.argv[1:4]
t = open(p, encoding="utf-8").read().replace("__EP_PY__", py).replace("__EP_BRIDGE__", br)
json.loads(t)                      # must stay valid JSON
open(p, "w", encoding="utf-8").write(t)
print("[3] hooks.json rendered for", br)
EOF

echo "[4] installing to: $DEST   (sudo password prompt is expected)"
sudo mkdir -p "$ROOT"
[[ -d "$DEST" ]] && sudo mv "$DEST" "$DEST.bak-$(date +%Y%m%d%H%M%S)" && echo "    previous copy backed up"
sudo cp -R "$STAGE/ep-desktop-bridge" "$DEST"
sudo chmod -R a+rX,go-w "$DEST"      # must stay world-READABLE or Claude Desktop (non-root) cannot load it
ls -la "$DEST" "$DEST/hooks"
echo "INSTALLED. Cmd+Q Claude Desktop, reopen, start a NEW session."
echo "Verify: tail -n 5 $EP_HOME/claude-code/desktop-hook.log   (new lines = hooks fired)"
