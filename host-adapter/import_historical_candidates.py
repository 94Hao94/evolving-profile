#!/usr/bin/env python3
"""Import historical candidate episodes into EP5 as isolated shadow records."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from lib.process_memory import ProcessMemoryStore

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path)
    ap.add_argument("--store", default=str(Path.home() / ".evolving-profile/process-memory/records.json"))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    candidates = list(report.get("candidates") or [])
    if args.limit: candidates = candidates[:args.limit]
    store = ProcessMemoryStore(args.store)
    existing = {str(r.get("historical_candidate_id")) for r in store.all() if r.get("historical_candidate_id")}
    imported = 0
    for c in candidates:
        cid = f"hist:{c.get('session_id')}:{c.get('prompt_line')}"
        if cid in existing: continue
        locator = f"codex_thread_history:{c.get('session_id')}:{c.get('prompt_line')}"
        trace = store.record_trajectory({
            "task_archetype": [c.get("task_archetype") or "other"],
            "process_dimensions": c.get("process_dimensions") or ["observation"],
            "phase": "recover" if "recovery" in (c.get("process_dimensions") or []) else "observe",
            "outcome": "recovered" if c.get("has_verification_signal") else "ambiguous",
            "text": "历史候选片段：" + " ".join(c.get("source_excerpt") or [])[:2800],
            "agent": {"role": "historical-codex-agent", "host": "codex"},
            "model_profile": {"family": "historical_unknown", "version": "pre_ep5_cutoff"},
            "environment_fingerprint": {"host": "codex_thread_history", "cutoff": c.get("cutoff")},
            "primary_context": {"session_id": c.get("session_id")},
            "failure_signature": c.get("signal_types") or [],
            "source_trace_ids": [locator], "historical_candidate_id": cid, "rollout_state": "shadow",
        })
        episode = store.promote_episode(trace["process_memory_id"], {
            "text": "历史失败事件候选：" + " ".join(c.get("source_excerpt") or [])[:2800],
            "failure_signature": c.get("signal_types") or [],
            "repair_actions": ["历史候选，等待原文回读和独立验证"],
            "verification_evidence": [{"verifier_kind": "source_check", "status": "passed", "source": locator, "scope": "episode_existence_only"}],
            "transfer_scope": {"transfer_status": "unknown"}, "historical_candidate_id": cid, "rollout_state": "shadow",
        })
        data = store._read()
        stored = next(r for r in data["records"] if r.get("process_memory_id") == episode["process_memory_id"])
        stored["rollout_state"] = "shadow"; stored["historical_candidate_id"] = cid
        store._write(data); imported += 1
    print(json.dumps({"schema":"evolving-profile.historical-import.v1","imported":imported,"requested":len(candidates),"read_only_source":True,"default_retrieval":"excluded_until_verified"}, ensure_ascii=False))
    return 0

if __name__ == "__main__": raise SystemExit(main())
