#!/usr/bin/env python3
"""Claude Desktop <-> EP compatibility health check. READ-ONLY: never writes, never calls a model, never restarts anything.

  python ep_desktop_health.py            human report, exit 1 if any FAIL
  python ep_desktop_health.py --json     machine-readable

Levels: OK / WARN (look at it) / FAIL (desktop compatibility is broken or EP is down).
"""
import argparse, collections, glob, json, os, sqlite3, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
EP = HOME / ".evolving-profile"
CC = EP / "claude-code"
sys.path.insert(0, str(CC / "compat"))
RESULTS = []


def add(level, name, detail):
    RESULTS.append({"level": level, "check": name, "detail": detail})


def tail_lines(path, max_bytes=400_000):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2); n = f.tell(); f.seek(max(0, n - max_bytes))
            data = f.read().decode("utf-8", "replace").splitlines()
        return data[1:] if n > max_bytes else data
    except OSError:
        return []


def jsonl(lines):
    for l in lines:
        try:
            yield json.loads(l)
        except Exception:
            continue


def age_s(path):
    return time.time() - os.path.getmtime(path)


def parse_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def check_api():
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open("http://127.0.0.1:12079/health", timeout=5) as r:
            d = json.loads(r.read(4000).decode())
        up_ok = d.get("status") == "healthy"
        func = d.get("functional_status", "healthy")
        if not up_ok:
            level, note = "FAIL", ""
        elif func != "healthy":
            # controller.py sets 'degraded' when the MOST RECENT request errored and flips back to 'healthy' on the next success:
            # a last-request indicator, not a persistent outage. /health does not expose last_error.
            level, note = "WARN", " (functional_status mirrors the controller's most recent request; re-run in a minute, it resets on the next success)"
        else:
            level, note = "OK", ""
        add(level, "EP API /health", f"status={d.get('status')} functional={func} version={d.get('version')} db={d.get('upstream', {}).get('database')}{note}")
    except Exception as e:
        add("FAIL", "EP API /health", f"unreachable: {type(e).__name__}: {e}")


def check_patches():
    try:
        import desktop_compat_patches as P
        st = P.states(EP / "runtime" / "host-adapter")
        bad = {k: v for k, v in st.items() if v != "applied"}
        if bad:
            add("FAIL", "compat patches", f"NOT intact {bad} -> run: python {CC}/compat/desktop_compat_patches.py apply")
        else:
            add("OK", "compat patches", "retain.py, retention_worker.py, recall.py, lib/session_paths.py all applied")
    except Exception as e:
        add("FAIL", "compat patches", f"cannot evaluate: {type(e).__name__}: {e}")


def check_files():
    problems = []
    for name in ("hook_bridge_desktop.py", "desktop_rollout.py"):
        p = CC / name
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        except Exception as e:
            problems.append(f"{name}: {type(e).__name__}")
    off = (CC / "desktop-rollout.off").exists()
    add("FAIL" if problems else "OK", "bridge + converter files", "compile OK" if not problems else "; ".join(problems))
    if off:
        add("WARN", "rollout kill switch", "desktop-rollout.off exists: converter is DISABLED, scenario summaries get no new desktop chats")


def check_plugin():
    d = Path("/Library/Application Support/Claude/org-plugins/ep-desktop-bridge")
    try:
        hooks = json.loads((d / "hooks" / "hooks.json").read_text())["hooks"]
        want = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "Stop"}
        miss = want - set(hooks)
        (d / ".claude-plugin" / "plugin.json").read_text()
        add("FAIL" if miss else "OK", "Claude Desktop hook plugin", f"installed, events present: {len(want) - len(miss)}/6" + (f", missing {sorted(miss)}" if miss else ""))
    except Exception as e:
        add("FAIL", "Claude Desktop hook plugin", f"not readable at {d}: {type(e).__name__} (hooks will not fire; reinstall with install_ep_desktop_plugin.sh)")


def check_hook_log():
    rows = [r for r in jsonl(tail_lines(CC / "desktop-hook.log")) if "ts" in r]
    cutoff = time.time() - 24 * 3600
    recent = [r for r in rows if (parse_ts(r["ts"]) or 0) >= cutoff and not str(r.get("session", "")).startswith(("desktop-brid", "11111111"))]
    if not recent:
        add("WARN", "hook activity (24h)", "no desktop hook events in the last 24h (fine if Claude Desktop was not used)")
        return
    ev = collections.Counter(r["event"] for r in recent)
    errs = [r for r in recent if r.get("error") or str(r.get("rollout", "")).startswith(("error", "bridge_error")) or r.get("flush_error") or r.get("adapter_rc") not in (0, None)]
    last = max(parse_ts(r["ts"]) or 0 for r in recent)
    add("FAIL" if errs else "OK", "hook activity (24h)", f"{len(recent)} events {dict(ev)}; last {int((time.time() - last) / 60)} min ago; problem rows: {len(errs)}" +
        (f" e.g. {({k: errs[-1].get(k) for k in ('event', 'adapter_rc', 'rollout', 'error', 'flush_error', 'stderr_head')})}" if errs else ""))


def check_rollouts():
    files = sorted(glob.glob(str(CC / "rollouts" / "**" / "rollout-*.jsonl"), recursive=True))
    pend = sorted(glob.glob(str(CC / "rollouts-pending" / "*.json")))
    if not files:
        add("WARN", "desktop rollouts", "none yet")
        return
    newest = min(age_s(f) for f in files) / 60
    stuck = [p for p in pend if age_s(p) > 3 * 1200]
    add("WARN" if stuck else "OK", "desktop rollouts", f"{len(files)} file(s), newest written {newest:.0f} min ago; pending markers {len(pend)}" +
        (f", {len(stuck)} older than 60 min (flush happens on the next session/prompt/stop; transcript is intact)" if stuck else ""))


def check_queue():
    qp = EP / "codex" / "state" / "retention-queue.json"
    try:
        q = json.loads(qp.read_text())
        items = q.get("items", [])
        mix = collections.Counter((i.get("metadata") or {}).get("origin_agent", "<none>") for i in items)
        oldest = max(((time.time() - (parse_ts(i.get("captured_at")) or time.time())) for i in items), default=0) / 3600
        ws = json.loads((EP / "retention" / "worker-state.json").read_text())
        held = [i for i in items if i.get("retention_quarantine") or i.get("retention_origin_hold")]
        held_desktop = [i for i in held if (i.get("metadata") or {}).get("origin_agent") == "claude-desktop"]
        held_other = len(held) - len(held_desktop)
        if held_desktop:
            level = "FAIL"      # desktop data is being refused by EP's write path
        elif held_other or oldest > 3:
            level = "WARN"      # EP's own retry-exhausted quarantine of non-desktop batches: raw text is kept in the queue, not lost
        else:
            level = "OK"
        note = ""
        if held_desktop:
            note = f" ; {len(held_desktop)} DESKTOP item(s) quarantined"
        elif held_other:
            note = f" ; {held_other} non-desktop item(s) quarantined by EP after exhausted retries (raw text kept in the queue; not caused by the desktop patches)"
        add(level, "write queue", f"{len(items)} item(s), oldest {oldest:.1f} h, origin mix {dict(mix)}; worker status={ws.get('status')} (submitted {ws.get('submitted_total')} / completed {ws.get('completed_total')}){note}")
    except Exception as e:
        add("FAIL", "write queue", f"unreadable: {type(e).__name__}: {e}")


def check_ingress():
    rows = list(jsonl(tail_lines(EP / "audit" / "prompt-ingress.jsonl", 300_000)))[-100:]
    mix = collections.Counter(r.get("host_id") for r in rows)
    try:   # only judge prompts after the recall.py patch went live; older rows legitimately say 'codex'
        stamp = (CC / "host-id-patch.stamp").read_text().strip()
        patched_at = datetime.strptime(stamp, "%Y%m%d%H%M%S").timestamp()
    except Exception:
        patched_at = 0
    desk_codex = [r for r in rows if r.get("cwd") == "/private/var/empty" and r.get("host_id") == "codex"
                  and (parse_ts(r.get("at")) or 0) > max(time.time() - 3600, patched_at)]
    add("WARN" if desk_codex else "OK", "recall receipts host_id", f"last {len(rows)} prompts: {dict(mix)}" + (f" ; {len(desk_codex)} desktop-looking prompt(s) since the patch still tagged codex (bridge env not reaching recall.py?)" if desk_codex else ""))


def check_context():
    try:
        db = sqlite3.connect(f"file:{EP / 'context' / 'context-incremental.sqlite'}?mode=ro", uri=True)
        by = collections.Counter(r[0] for r in db.execute("select status from jobs"))
        ids = set()
        for f in glob.glob(str(CC / "rollouts" / "**" / "rollout-*.jsonl"), recursive=True):
            ids.add(f[-42:-6])
        desk = {}
        for sid in ids:
            r = db.execute("select status, error_code from jobs where session_id=?", (sid,)).fetchone()
            desk[sid[:8]] = f"{r[0]}" + (f"/{r[1]}" if r and r[1] else "") if r else "NO JOB"
        failed_desk = [k for k, v in desk.items() if v.startswith("failed")]
        # a failed session whose user side is only scheduler wrappers is a historical scheduled run (written before the converter
        # learned to skip those); it is not a failure of a real conversation
        def automated_only(prefix):
            for f in glob.glob(str(CC / "rollouts" / "**" / f"rollout-*{prefix}*.jsonl"), recursive=True):
                users = []
                for line in open(f, encoding="utf-8"):
                    r = json.loads(line)
                    if r.get("type") == "response_item" and r["payload"].get("role") == "user":
                        users.append("".join(c.get("text", "") for c in r["payload"]["content"]))
                return bool(users) and all(u.startswith(("<scheduled-task", "[SCHEDULED TASK - AUTOMATED FIRING")) for u in users)
            return False
        real_failed = [k for k in failed_desk if not automated_only(k)]
        hist_sched = [k for k in failed_desk if k not in real_failed]
        level = "FAIL" if real_failed else ("WARN" if hist_sched else "OK")
        note = ""
        if real_failed:
            note = " <- a desktop conversation FAILED: " + ",".join(real_failed)
        elif hist_sched:
            note = f" ; {len(hist_sched)} failed job(s) are historical scheduled runs ({','.join(hist_sched)}), no longer produced"
        add(level, "scenario summaries", f"jobs {dict(by)}; desktop sessions: {desk or 'none'}{note}")
        nojob = [k for k, v in desk.items() if v == "NO JOB"]
        if nojob:
            add("WARN", "scenario discovery", f"{len(nojob)} desktop rollout(s) not yet picked up by the context worker (it runs every 30s; check again shortly)")
    except Exception as e:
        add("FAIL", "scenario summaries", f"cannot read context db: {type(e).__name__}: {e}")


def check_error_logs():
    notes = []
    for name in ("retention-worker.error.log", "context-worker.error.log"):
        p = EP / "logs" / name
        if p.exists() and p.stat().st_size and age_s(p) < 24 * 3600:
            notes.append(f"{name} {p.stat().st_size}B modified {int(age_s(p) / 60)} min ago")
    add("WARN" if notes else "OK", "worker error logs", "; ".join(notes) or "empty / untouched in 24h")


def last_embedding_model(logname):
    """Model id from the most recent 'initializing ONNX provider' line of a process log (grep keeps this fast on 80MB logs)."""
    import subprocess
    r = subprocess.run(f"grep -a 'initializing ONNX provider with model' '{EP / 'logs' / logname}' | tail -n 1", shell=True, capture_output=True, text=True, timeout=30)
    line = r.stdout.strip()
    if not line:
        return None, None
    m = line.split("with model ", 1)[-1].split(" (", 1)[0].strip()
    return m, line[:19]


def check_embeddings():
    """Write path (worker) and read path (API) must embed in the SAME vector space, otherwise vector search returns noise.
    Found 2026-10-24: the API loads config/retrieval-models.env (MiniLM) but the worker launcher does not (still e5)."""
    api, api_at = last_embedding_model("api-shadow.log")
    wrk, wrk_at = last_embedding_model("worker.log")
    if not api or not wrk:
        add("WARN", "embedding model consistency", f"cannot read both init lines (api={api}, worker={wrk})")
    elif api != wrk:
        add("FAIL", "embedding model consistency", f"READ path (API, since {api_at}) uses {api} but WRITE path (worker, since {wrk_at}) uses {wrk}: query vectors and stored vectors are in different spaces, vector search is ~random (measured top-1 0.01 vs 0.94 consistent). Fix: make both load the same model (see compat/README.md)")
    else:
        add("OK", "embedding model consistency", f"API and worker both embed with {api}")


def check_hosts():
    """Which Claude hosts reached EP in the last 24h, and is the legacy entry point still the host-aware shim?"""
    rows = [r for r in jsonl(tail_lines(CC / "desktop-hook.log", 1_500_000)) if "ts" in r and (parse_ts(r["ts"]) or 0) >= time.time() - 24 * 3600
            and not str(r.get("session", "")).startswith(("desktop-brid", "11111111", "hostaware-"))]
    by = collections.Counter(r.get("host", "<pre-hostaware>") for r in rows)
    unknown = collections.Counter(r.get("entrypoint", "") for r in rows if r.get("host") == "claude-code")
    shim = "runpy" in (CC / "hook_bridge.py").read_text(encoding="utf-8", errors="replace")
    msg = f"24h events by host {dict(by)}; legacy hook_bridge.py is {'the host-aware shim' if shim else 'the OLD bridge (tool output would be stored as user speech!)'}"
    if unknown:
        msg += f"; unrecognised Claude entrypoints seen: {dict(unknown)} (treated as generic claude-code; add to detect_host if they matter)"
    add("FAIL" if not shim else ("WARN" if unknown else "OK"), "claude hosts (desktop / cli)", msg)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json", action="store_true"); a = ap.parse_args()
    for fn in (check_api, check_patches, check_files, check_plugin, check_hook_log, check_rollouts, check_queue, check_ingress, check_context, check_error_logs, check_embeddings, check_hosts):
        try:
            fn()
        except Exception as e:
            add("FAIL", fn.__name__, f"check crashed: {type(e).__name__}: {e}")
    worst = "FAIL" if any(r["level"] == "FAIL" for r in RESULTS) else ("WARN" if any(r["level"] == "WARN" for r in RESULTS) else "OK")
    if a.json:
        print(json.dumps({"overall": worst, "checked_at": datetime.now(timezone.utc).isoformat(), "results": RESULTS}, ensure_ascii=False, indent=1))
    else:
        print(f"EP x Claude Desktop health  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        for r in RESULTS:
            print(f"  [{r['level']:4s}] {r['check']:28s} {r['detail']}")
        print(f"overall: {worst}")
    return 1 if worst == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
