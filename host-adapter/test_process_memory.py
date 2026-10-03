import json

import pytest

from lib.process_memory import (
    ProcessMemoryStore,
    compatibility_match,
    compute_intervention,
    normalize_record,
)


def base_trace(**overrides):
    value = {
        "kind": "trace",
        "task_archetype": ["software_engineering"],
        "process_dimensions": ["debugging", "verification"],
        "phase": "recover",
        "outcome": "recovered",
        "maturity": "observed",
        "agent": {"role": "coding-agent", "host": "codex"},
        "model_profile": {"family": "model-a", "version": "1", "capability_fingerprint": "fp-a"},
        "environment_fingerprint": {"toolchain": ["python"], "verifier": "pytest"},
        "source_trace_ids": ["trace-1"],
        "verification_evidence": [],
        "preconditions": ["pytest available"],
        "text": "A test failed, then the missing import was repaired and verified.",
    }
    value.update(overrides)
    return value


def test_normalize_record_adds_version_and_rejects_unknown_kind():
    result = normalize_record(base_trace())
    assert result["schema_version"] == "agent-process-memory.v1"
    assert result["process_memory_id"]
    assert result["selection_exposure"] == {"shown": 0, "selected": 0, "skipped": 0}
    assert result["intervention_level"] == "hint"
    assert result["drift_status"] == "stable"
    assert "model_capability_fingerprint" in result
    with pytest.raises(ValueError, match="process_memory_kind_invalid"):
        normalize_record(base_trace(kind="not-a-kind"))


def test_store_keeps_trajectory_separate_and_promotes_only_with_verifier(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    trace = store.record_trajectory(base_trace())
    assert trace["kind"] == "trace"
    with pytest.raises(ValueError, match="verification_evidence_required"):
        store.promote_episode(trace["process_memory_id"], {"text": "root cause"})

    episode = store.promote_episode(
        trace["process_memory_id"],
        {
            "text": "Missing import caused the test failure.",
            "failure_signature": ["ModuleNotFoundError"],
            "repair_actions": ["add the import"],
            "verification_evidence": [{"verifier_kind": "automated_test", "status": "passed", "id": "pytest-1"}],
        },
    )
    assert episode["kind"] == "episode"
    assert episode["maturity"] == "verified"
    assert episode["source_trace_ids"] == [trace["process_memory_id"]]


def test_pattern_and_skill_require_repeated_verified_evidence(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    first = store.record_trajectory(base_trace(source_trace_ids=["raw-a"], text="first"))
    second = store.record_trajectory(base_trace(source_trace_ids=["raw-b"], text="second"))
    ep1 = store.promote_episode(first["process_memory_id"], {"text": "same repair", "verification_evidence": [{"verifier_kind": "automated_test", "status": "passed", "id": "a"}]})
    ep2 = store.promote_episode(second["process_memory_id"], {"text": "same repair", "verification_evidence": [{"verifier_kind": "automated_test", "status": "passed", "id": "b"}]})
    pattern = store.promote_pattern([ep1["process_memory_id"], ep2["process_memory_id"]], {"text": "Use the import check before rerunning tests."})
    assert pattern["kind"] == "pattern"
    assert pattern["maturity"] == "replicated"
    skill = store.promote_skill([pattern["process_memory_id"]], {"text": "Import failure recovery runbook"})
    assert skill["kind"] == "skill"
    assert skill["maturity"] == "verified"


def test_compatibility_and_intervention_are_task_local():
    record = normalize_record(base_trace())
    assert compatibility_match(record, {"model_family": "model-a", "model_version": "1", "toolchain": ["python"]})
    assert not compatibility_match(record, {"model_family": "model-b", "model_version": "1", "toolchain": ["python"]})
    assert compute_intervention({"confidence": "high", "failure_evidence": 0}, {})["intervention_level"] == "hint"
    assert compute_intervention({"confidence": "unknown", "failure_evidence": 2}, {})["intervention_level"] == "scaffold"


def test_store_search_does_not_inject_incompatible_records(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    a = store.record_trajectory(base_trace(model_profile={"family": "model-a", "version": "1"}))
    b = store.record_trajectory(base_trace(source_trace_ids=["trace-2"], model_profile={"family": "model-b", "version": "1"}))
    a = store.promote_episode(a["process_memory_id"], {"text": "verified test failure repair", "verification_evidence": [{"verifier_kind": "automated_test", "status": "passed", "id": "a"}]})
    b = store.promote_episode(b["process_memory_id"], {"text": "verified test failure repair", "verification_evidence": [{"verifier_kind": "automated_test", "status": "passed", "id": "b"}]})
    result = store.search("test failed", compatibility={"model_family": "model-a", "model_version": "1"}, limit=10)
    assert [item["process_memory_id"] for item in result] == [a["process_memory_id"]]


def test_process_draft_is_only_for_recovery_and_stays_out_of_default_search(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    draft = store.record_process_draft({
        "task_archetype": ["software_engineering"],
        "process_dimensions": ["debugging", "verification"],
        "phase": "recover",
        "text": "先遇到导入错误，换路线后通过测试。",
        "failure_signature": ["ModuleNotFoundError"],
        "repair_actions": ["修正依赖"],
        "source_trace_ids": ["trace-1"],
        "verification_evidence": [{"verifier_kind": "automated_test", "status": "passed", "id": "test-1"}],
    })
    assert draft["kind"] == "process_draft"
    assert draft["maturity"] == "diagnosed"
    assert store.search("导入错误") == []
    assert store.search("导入错误", include_unverified=True)[0]["process_memory_id"] == draft["process_memory_id"]


def test_process_draft_rejects_ordinary_success_and_long_text(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    with pytest.raises(ValueError, match="process_draft_requires_failure_or_repair"):
        store.record_process_draft({"task_archetype": ["other"], "phase": "deliver", "text": "正常完成"})
    with pytest.raises(ValueError, match="process_draft_too_long"):
        store.record_process_draft({"task_archetype": ["other"], "phase": "recover", "text": "x" * 3001, "failure_signature": ["x"], "source_trace_ids": ["trace-1"]})


def test_capability_observation_needs_independent_verifier(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    with pytest.raises(ValueError, match="capability_verifier_required"):
        store.record_capability_observation({"model_family": "model-a", "task_archetype": "software_engineering", "phase": "verify", "outcome": "success", "verifier_kind": "agent_self_report"})
    result = store.record_capability_observation({"model_family": "model-a", "task_archetype": "software_engineering", "phase": "verify", "outcome": "success", "verifier_kind": "automated_test", "status": "passed"})
    assert result["kind"] == "capability_observation"
    assert result["profile"]["sample_count"] == 1


def test_historical_skill_candidate_is_visible_but_not_retrievable(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    episodes = []
    for index in range(2):
        trace = store.record_trajectory({
            "task_archetype": ["document_office"],
            "process_dimensions": ["debugging", "verification"],
            "phase": "recover",
            "outcome": "recovered",
            "text": f"candidate trace {index}",
            "source_trace_ids": [f"source-{index}"],
            "model_profile": {"family": "historical_unknown", "version": "candidate"},
            "primary_context": {"scope": "history"},
        })
        episodes.append(store.promote_episode(trace["process_memory_id"], {
            "verification_evidence": [{"verifier_kind": "source_check", "status": "passed"}],
        }))
    patterns = []
    for episode in episodes:
        pattern = dict(episode)
        pattern["kind"] = "pattern"
        pattern["process_memory_id"] = f"pattern-{len(patterns)}"
        pattern["maturity"] = "diagnosed"
        pattern["rollout_state"] = "shadow"
        pattern["historical_candidate_id"] = f"candidate-{len(patterns)}"
        pattern["source_trace_ids"] = episode["source_trace_ids"]
        store._append(pattern)
        patterns.append(pattern)
    candidate = store.record_skill_candidate([row["process_memory_id"] for row in patterns], {"text": "candidate skill"})
    assert candidate["kind"] == "skill"
    assert candidate["maturity"] == "diagnosed"
    assert candidate["status"] == "candidate"
    assert all(row.get("kind") != "skill" for row in store.search("candidate skill"))


def test_verified_process_is_promoted_automatically_without_human_confirmation(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    for index in range(2):
        store.record_trajectory({
            "task_archetype": ["software_engineering"],
            "process_dimensions": ["debugging", "verification"],
            "phase": "recover",
            "outcome": "recovered",
            "text": "automatic repair receipt",
            "failure_signature": ["pytest_failure"],
            "repair_actions": ["apply minimal repair"],
            "verification_evidence": [{"verifier_kind": "automated_test", "status": "passed", "task_id": f"auto-{index}"}],
            "primary_context": {"task_id": f"auto-{index}"},
        })
    result = store.auto_promote_verified_process()
    assert result["episodes"] == 2
    assert result["patterns"] == 1
    assert sum(row.get("kind") == "episode" for row in store.all()) == 2
    assert sum(row.get("kind") == "pattern" for row in store.all()) == 1


def test_source_locator_only_cannot_auto_promote(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    store.record_trajectory({
        "task_archetype": ["document_office"], "process_dimensions": ["verification"],
        "phase": "verify", "outcome": "recovered", "text": "historical locator",
        "verification_evidence": [{"verifier_kind": "source_check", "status": "passed", "scope": "episode_existence_only"}],
        "primary_context": {"session_id": "history-1"},
    })
    assert store.auto_promote_verified_process() == {"episodes": 0, "patterns": 0}
