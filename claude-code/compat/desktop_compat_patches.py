#!/usr/bin/env python3
"""Idempotent re-apply of the Claude Desktop compatibility patches to EP's host-adapter.

Why this exists: EP releases keep copies of host-adapter under runtime/releases/. If an EP upgrade overwrites the live
files, desktop compatibility silently disappears (no error, data is just mislabelled / invisible to scenario summaries).
This module is the single source of truth for the four in-place edits and can detect and repair that.

Patch groups (each group is all-or-nothing per file):
  retain.py            stamp queue items with origin_agent (env HINDSIGHT_AGENT_NAME, default 'codex')
  retention_worker.py  copy origin_agent into the Bank metadata of a submitted batch   (2 edits that must travel together)
  recall.py            prompt-ingress receipt host_id from env HINDSIGHT_AGENT_NAME     (default 'codex')
  lib/session_paths.py add EP's own desktop rollout dir to the Codex-layout session roots

States per file:  applied | pristine | partial (refuse) | anchor_missing (refuse, upstream changed, needs a human)

usage:
  desktop_compat_patches.py check [--adapter DIR]            read-only, exit 1 if anything is not 'applied'
  desktop_compat_patches.py apply [--adapter DIR] [--dry-run] backup + atomic replace for 'pristine' files only
"""
import argparse, hashlib, os, shutil, sys, tempfile, time
from pathlib import Path

DEFAULT_ADAPTER = Path.home() / ".evolving-profile" / "runtime" / "host-adapter"

GROUPS = {
    "retain.py": [(
        "metadata={'source':'codex-hook-token-batch', 'session_id':session_id,",
        "metadata={'source':'codex-hook-token-batch', 'origin_agent':(os.environ.get('HINDSIGHT_AGENT_NAME') or 'codex')[:40], 'session_id':session_id,",
    )],
    "retention_worker.py": [
        (
            "    item={'content':batch['content'],'document_id':'codex-batch-'+batch['batch_id'],",
            "    _rows=batch.get('items') or locals().get('chosen') or []\n"
            "    _origin=','.join(sorted({str((r.get('metadata') or {}).get('origin_agent') or 'codex') for r in _rows})) or 'codex'\n"
            "    item={'content':batch['content'],'document_id':'codex-batch-'+batch['batch_id'],",
        ),
        (
            "'metadata':{'source':'codex-hook-token-batch','project':batch['project'],",
            "'metadata':{'source':'codex-hook-token-batch','origin_agent':_origin,'project':batch['project'],",
        ),
    ],
    "recall.py": [(
        '            "host_id": "codex",\n',
        '            "host_id": os.environ.get("HINDSIGHT_AGENT_NAME") or "codex",\n',
    )],
    "lib/session_paths.py": [(
        "    if root.name=='sessions':roots.append(root.parent/'archived_sessions')\n    return list(dict.fromkeys(roots))\n",
        "    if root.name=='sessions':roots.append(root.parent/'archived_sessions')\n"
        "    # Claude Desktop chats are converted by EP's desktop bridge into Codex-shaped rollouts under EP's own state dir\n"
        "    # (never under ~/.codex). Only the real Codex layout opts in, so any other root is untouched.\n"
        "    if root.name=='sessions' and root.parent.name=='.codex':\n"
        "        roots.append(root.parent.parent/'.evolving-profile'/'claude-code'/'rollouts')\n"
        "    return list(dict.fromkeys(roots))\n",
    )],
}


def classify(text, edits):
    """-> 'applied' | 'pristine' | 'partial' | 'anchor_missing'"""
    done = [new in text for _, new in edits]
    if all(done):
        return "applied"
    if any(done):
        return "partial"
    if all(old in text for old, _ in edits):
        return "pristine"
    return "anchor_missing"


def apply_edits(text, edits):
    for old, new in edits:
        if text.count(old) != 1:
            raise ValueError(f"anchor must occur exactly once, found {text.count(old)}: {old[:60]!r}")
        text = text.replace(old, new)
    return text


def states(adapter):
    out = {}
    for rel, edits in GROUPS.items():
        p = Path(adapter) / rel
        out[rel] = classify(p.read_text(encoding="utf-8"), edits) if p.is_file() else "file_missing"
    return out


def cmd_check(adapter):
    st = states(adapter)
    for rel, s in st.items():
        print(f"  [{'OK' if s == 'applied' else 'FAIL'}] {rel:22s} {s}")
    bad = [r for r, s in st.items() if s != "applied"]
    print("desktop compat patches:", "all applied" if not bad else f"NOT intact: {', '.join(bad)}")
    return 0 if not bad else 1


def cmd_apply(adapter, dry):
    adapter = Path(adapter)
    st = states(adapter)
    ts = time.strftime("%Y%m%d%H%M%S")
    rc = 0
    for rel, s in st.items():
        p = adapter / rel
        if s == "applied":
            print(f"  [skip]  {rel}: already applied")
        elif s == "pristine":
            new_text = apply_edits(p.read_text(encoding="utf-8"), GROUPS[rel])
            compile(new_text, str(p), "exec")                  # refuse to install something that does not compile (nothing written yet)
            if dry:
                print(f"  [dry]   {rel}: would patch ({len(GROUPS[rel])} edit(s))")
                continue
            tmp = p.with_name(p.name + f".new-{ts}")
            tmp.write_text(new_text, encoding="utf-8")
            os.chmod(tmp, p.stat().st_mode & 0o777)
            backup = p.with_name(p.name + f".pre-reapply-{ts}")
            shutil.copy2(p, backup)
            os.replace(tmp, p)
            print(f"  [done]  {rel}: patched (backup {backup.name})")
        else:
            rc = 1
            print(f"  [REFUSE] {rel}: state={s} -> not touching it; upstream changed or a previous patch is half-applied, a human must look")
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "apply"])
    ap.add_argument("--adapter", default=str(DEFAULT_ADAPTER))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    return cmd_check(a.adapter) if a.command == "check" else cmd_apply(a.adapter, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
