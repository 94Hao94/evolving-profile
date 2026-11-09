#!/bin/zsh
# Install / refresh the Claude (Desktop + CLI) integration for an existing Evolving Profile install.
# Codex is never touched: ~/.codex/* and codex.json are not read or written.
#
#   zsh claude-code/install.sh                       kit + EP patches + CLI hooks            (no sudo)
#   zsh claude-code/install.sh --desktop-plugin      ... plus the Claude Desktop hook plugin (asks for sudo once)
#   zsh claude-code/install.sh --dry-run             show every step, change nothing
#   zsh claude-code/install.sh --uninstall           remove CLI hooks (+ desktop plugin with --desktop-plugin); the kit stays
#
# Environment: EP_HOME (default ~/.evolving-profile), EP_API_SRC (API source dir; enables the quote-repair patch)
set -e
HERE=${0:A:h}
EP_HOME=${EP_HOME:-$HOME/.evolving-profile}
DEST=$EP_HOME/claude-code
ADAPTER=$EP_HOME/runtime/host-adapter
PY=$EP_HOME/runtime/python-3.11/bin/python; [[ -x $PY ]] || PY=$(command -v python3)
DRY=0; PLUGIN=0; UNINSTALL=0
for a in "$@"; do case $a in --dry-run) DRY=1;; --desktop-plugin) PLUGIN=1;; --uninstall) UNINSTALL=1;; *) echo "unknown option $a"; exit 2;; esac; done
run() { if [[ $DRY -eq 1 ]]; then echo "   [dry-run] $*"; else "$@"; fi }

echo "EP_HOME=$EP_HOME  python=$PY"
[[ -d $EP_HOME ]] || { echo "ABORT: $EP_HOME not found (install Evolving Profile first)"; exit 1; }

if [[ $UNINSTALL -eq 1 ]]; then
  echo "== uninstall"; run $PY $HERE/install_cli_hooks.py --uninstall --ep-home $EP_HOME
  if [[ $PLUGIN -eq 1 ]]; then run zsh $HERE/install-desktop-plugin.sh --uninstall; fi
  echo "The kit in $DEST and the EP file patches are left in place (they are inert without hooks)."; exit 0
fi

echo "== 1. copy the kit to $DEST (logs, rollouts and transcripts already there are kept)"
run mkdir -p $DEST
for f in hook_bridge_desktop.py hook_bridge.py desktop_rollout.py install_cli_hooks.py install-desktop-plugin.sh install.sh; do
  [[ $HERE == $DEST ]] || run cp $HERE/$f $DEST/$f
done
[[ $HERE == $DEST ]] || { run rm -rf $DEST/compat $DEST/desktop-plugin; run cp -R $HERE/compat $HERE/desktop-plugin $DEST/; }

echo "== 2. in-place edits of the installed host-adapter (idempotent; backups *.pre-reapply-<ts>)"
if [[ -d $ADAPTER ]]; then
  run $PY -I $DEST/compat/desktop_compat_patches.py apply --adapter $ADAPTER
else
  echo "   skipped: $ADAPTER not found"
fi

echo "== 3. optional API patch (quote repair for fact extraction)"
if [[ -n "$EP_API_SRC" ]]; then run $PY -I $DEST/compat/quote_repair_patch.py apply --api $EP_API_SRC; else echo "   skipped: set EP_API_SRC=<api source dir> to apply (the release package already contains it)"; fi

echo "== 4. Claude Code CLI hooks -> ~/.claude/settings.json"
run $PY $HERE/install_cli_hooks.py --ep-home $EP_HOME

if [[ $PLUGIN -eq 1 ]]; then echo "== 5. Claude Desktop hook plugin (sudo)"; run zsh $HERE/install-desktop-plugin.sh; else echo "== 5. Claude Desktop hook plugin: skipped (add --desktop-plugin)"; fi

echo "== done. Verify:  $PY $DEST/compat/ep_desktop_health.py"
echo "   Restart Claude Desktop (Cmd+Q) and open a NEW session so it loads the plugin."
