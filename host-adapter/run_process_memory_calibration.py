#!/usr/bin/env python3
"""Run two deterministic debugging calibrations and promote a shadow Skill."""
from __future__ import annotations
import json, subprocess, tempfile
from pathlib import Path
from lib.process_memory import ProcessMemoryStore

def run_case(root: Path, name: str, body: str, fix: str, store: ProcessMemoryStore):
    task_id = f"calibration:{name}"
    test = root / f"test_{name}.py"
    test.write_text(body, encoding="utf-8")
    failed = subprocess.run(["python3", "-m", "pytest", "-q", str(test)], cwd=root, capture_output=True, text=True)
    test.write_text(fix, encoding="utf-8")
    passed = subprocess.run(["python3", "-m", "pytest", "-q", str(test)], cwd=root, capture_output=True, text=True)
    if failed.returncode == 0 or passed.returncode != 0:
        raise RuntimeError(f"calibration_verifier_failed:{name}")
    trace = store.record_trajectory({
        "task_archetype": ["software_engineering"], "process_dimensions": ["debugging", "verification"], "phase": "recover", "outcome": "recovered",
        "text": f"Calibration {name}: first pytest failed, repair applied, second pytest passed.", "agent": {"role": "coding-agent", "host": "codex"},
        "model_profile": {"family": "gpt-6.1-sol", "version": "current"}, "environment_fingerprint": {"toolchain": ["python", "pytest"]},
        "primary_context": {"task_id": task_id, "project_id": "ep5-calibration", "session_id": task_id}, "failure_signature": ["pytest_failure"],
        "repair_actions": ["apply minimal source repair"], "source_trace_ids": [task_id],
    })
    return store.promote_episode(trace["process_memory_id"], {"text": f"Repeated debugging repair verified for {name}.", "failure_signature": ["pytest_failure"], "repair_actions": ["inspect failure, apply minimal repair, rerun verifier"], "verification_evidence": [{"verifier_kind": "automated_test", "status": "passed", "id": task_id}], "transfer_scope": {"transfer_status": "candidate"}, "rollout_state": "shadow"})

def main():
    root = Path(tempfile.mkdtemp(prefix="ep5-calibration-")); store = ProcessMemoryStore(Path.home() / ".evolving-profile/process-memory/records.json")
    cases = [
        ("missing_return", "def answer():\n    pass\n\ndef test_answer():\n    assert answer() == 42\n", "def answer():\n    return 42\n\ndef test_answer():\n    assert answer() == 42\n"),
        ("wrong_type", "def answer():\n    return '42'\n\ndef test_answer():\n    assert answer() == 42\n", "def answer():\n    return 42\n\ndef test_answer():\n    assert answer() == 42\n"),
    ]
    episodes = [run_case(root, *case, store) for case in cases]
    pattern = store.promote_pattern([e["process_memory_id"] for e in episodes], {"text": "When a deterministic test exposes a small return-value defect, inspect the failing assertion, apply the minimal return-value repair, and rerun the verifier.", "rollout_state": "shadow", "transfer_scope": {"transfer_status": "candidate"}})
    skill = store.promote_skill([pattern["process_memory_id"]], {"text": "Deterministic assertion failure recovery runbook: inspect the assertion, apply the smallest repair, rerun pytest, and keep the result in shadow until cross-model evaluation.", "rollout_state": "shadow", "transfer_scope": {"transfer_status": "candidate"}})
    print(json.dumps({"schema":"evolving-profile.calibration.v1","root":str(root),"episodes":len(episodes),"pattern":pattern["process_memory_id"],"skill":skill["process_memory_id"],"verifier":"pytest","rollout":"shadow"},ensure_ascii=False))
if __name__ == "__main__": main()
