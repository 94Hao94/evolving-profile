#!/usr/bin/env python3
"""Register the EP bridge as Claude Code CLI hooks in ~/.claude/settings.json.  Idempotent, reversible, never touches other keys.

  python3 install_cli_hooks.py                 install / refresh (backs up settings.json first)
  python3 install_cli_hooks.py --dry-run       print the resulting "hooks" block, change nothing
  python3 install_cli_hooks.py --uninstall     remove only the EP bridge entries
  options: --settings PATH   (default ~/.claude/settings.json)   --ep-home DIR   --python PATH

Claude Desktop (Cowork) does NOT read this file for its sessions - it uses the org plugin (see install-desktop-plugin.sh).
Both routes run the same host-aware bridge (hook_bridge_desktop.py), which detects the caller and tags every record.
"""
import argparse, json, os, shutil, sys, time
from pathlib import Path

MARK = "hook_bridge"   # any command containing this is considered ours
TOOL_MATCH_BASH = "^(Bash|Write|Edit|MultiEdit)$"
TOOL_MATCH_EP = "^mcp__evolving_profile_controller__(user_recall|user_research|read_research|read_source|find_sources|memory_check)$"


def build(py, bridge):
    def cmd(ev):
        return f'"{py}" "{bridge}" {ev}'

    def entry(ev, timeout, matcher=None):
        e = {"hooks": [{"type": "command", "command": cmd(ev), "timeout": timeout}]}
        if matcher:
            e["matcher"] = matcher
        return e

    return {
        "SessionStart": [entry("session", 10)],
        "UserPromptSubmit": [entry("recall", 65)],
        "PreToolUse": [entry("pretool", 6, TOOL_MATCH_BASH), entry("pretool", 6, TOOL_MATCH_EP)],
        "PostToolUse": [entry("posttool", 18)],
        "PreCompact": [entry("precompact", 8)],
        "Stop": [entry("retain", 45)],
    }


def is_ours(group):
    return any(MARK in (h.get("command") or "") for h in group.get("hooks", []))


def merged(settings, ours, uninstall):
    hooks = dict(settings.get("hooks") or {})
    for ev in set(hooks) | set(ours):
        kept = [g for g in hooks.get(ev, []) if not is_ours(g)]
        new = kept if uninstall else kept + ours.get(ev, [])
        if new:
            hooks[ev] = new
        else:
            hooks.pop(ev, None)
    out = dict(settings)
    if hooks:
        out["hooks"] = hooks
    else:
        out.pop("hooks", None)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--settings", default=str(Path.home() / ".claude" / "settings.json"))
    ap.add_argument("--ep-home", default=os.environ.get("EP_HOME", str(Path.home() / ".evolving-profile")))
    ap.add_argument("--python", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()
    ep = Path(a.ep_home)
    py = a.python or str(ep / "runtime" / "python-3.11" / "bin" / "python")
    if not Path(py).exists():
        py = sys.executable
    bridge = str(ep / "claude-code" / "hook_bridge_desktop.py")
    sp = Path(a.settings)
    try:
        cur = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    except Exception as e:
        raise SystemExit(f"cannot parse {sp}: {e} (not touching it)")
    new = merged(cur, build(py, bridge), a.uninstall)
    if new == cur:
        print("settings.json already up to date")
        return
    if a.dry_run:
        print(json.dumps(new.get("hooks", {}), indent=2, ensure_ascii=False))
        return
    sp.parent.mkdir(parents=True, exist_ok=True)
    if sp.exists():
        bk = sp.with_name(sp.name + ".pre-ep-" + time.strftime("%Y%m%d%H%M%S"))
        shutil.copy2(sp, bk)
        print("backup:", bk)
    tmp = sp.with_name(sp.name + ".tmp")
    tmp.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, sp)
    print("uninstalled EP hooks from" if a.uninstall else "installed EP hooks into", sp)


if __name__ == "__main__":
    main()
