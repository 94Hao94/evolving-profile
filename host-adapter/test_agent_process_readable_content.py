"""Characterize the real capability/trajectory shapes behind an empty recall.

Capability receipts contain aggregate metadata, not an execution narrative.
The public Agent tools include observed trajectories by default; a caller can
explicitly restrict retrieval to mature records. Neither path verifies claims.
"""
import json

import pytest

from lib.process_memory import ProcessMemoryStore, normalize_record
from lib.recall_relevance import apply_relevance_policy, classify_candidate


BODY = "Filter relevant rows before pagination offset calculation."


def capability_receipt(store):
    # Use the production writer: this is the same aggregate-only schema as
    # the live capability observations, with intentionally matching metadata.
    return store.record_capability_observation({
        "model_family": "pagination", "model_version": "v1",
        "task_archetype": "pagination", "phase": "verify",
        "outcome": "correct", "verifier_kind": "automated_test",
        "status": "passed",
    })


def test_real_capability_aggregate_cannot_supply_missing_execution_content(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    receipt = capability_receipt(store)
    before = store.path.read_bytes()
    page = store.search_page("pagination", task_archetype="pagination",
                             compatibility={"model_family": "pagination"})
    assert page["records"] == []
    assert page["relevance_audit"]["eligible_candidate_count"] == 1
    assert page["relevance_audit"]["exclusion_reasons"] == {"no_readable_candidate_content": 1}
    decision = page["relevance_audit"]["decisions"][0]
    assert decision["id"] == receipt["process_memory_id"]
    assert decision["level"] == "unknown"
    assert decision["execution_eligible"] is False
    assert store.path.read_bytes() == before


def test_mature_only_query_excludes_observed_body_without_misclassifying_it(tmp_path):
    store = ProcessMemoryStore(tmp_path / "records.json")
    trace = store.record_trajectory({"phase": "recover", "text": BODY})
    capability_receipt(store)
    before = store.path.read_bytes()
    mature = store.search_page("pagination", include_unverified=False)
    observed = store.search_page("pagination", include_unverified=True)
    assert mature["records"] == []
    assert mature["relevance_audit"]["scope_or_maturity_excluded_count"] == 1
    assert mature["relevance_audit"]["eligible_candidate_count"] == 1
    assert [row["process_memory_id"] for row in observed["records"]] == [trace["process_memory_id"]]
    assert observed["records"][0]["text"] == BODY
    assert observed["records"][0]["maturity"] == "observed"
    assert observed["records"][0]["truth_status"] == "unknown"
    assert observed["records"][0]["execution_eligible"] is False
    assert observed["relevance_audit"]["exclusion_reasons"] == {"no_readable_candidate_content": 1}
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("handler_name", ["search_agent_process_memory", "research_agent_process_memory"])
def test_native_agent_defaults_expose_observed_body_and_honor_explicit_maturity_filter(
        tmp_path, monkeypatch, handler_name):
    import evolving_profile_controller_mcp as mcp

    store = ProcessMemoryStore(tmp_path / "records.json")
    trace = store.record_trajectory({"phase": "recover", "text": BODY})
    capability_receipt(store)
    monkeypatch.setattr(mcp, "PROCESS_MEMORY_PATH", store.path)
    monkeypatch.setattr(mcp, "PROCESS_MEMORY_WORKSPACE_ROOT", tmp_path / "workspaces")
    monkeypatch.setattr(mcp, "runtime_disabled", lambda *_args: None)
    monkeypatch.setattr(mcp, "load_runtime_settings", lambda: {})
    before = store.path.read_bytes()
    handler = getattr(mcp, handler_name)
    arguments = {"query": "pagination", "workspace_id": "readable-body"}
    default = json.loads(handler(arguments)["content"][0]["text"])
    mature = json.loads(handler({**arguments, "include_unverified": False})["content"][0]["text"])
    assert default["returned_count"] == 1
    assert default["records"][0]["process_memory_id"] == trace["process_memory_id"]
    assert default["records"][0]["text"] == BODY
    assert default["records"][0]["truth_status"] == "unknown"
    assert default["records"][0]["execution_eligible"] is False
    assert default["automatic_injection"] is False
    assert default["relevance_audit"]["exclusion_reasons"] == {"no_readable_candidate_content": 1}
    assert mature["returned_count"] == 0
    assert mature["relevance_audit"]["eligible_candidate_count"] == 1
    assert mature["relevance_audit"]["scope_or_maturity_excluded_count"] == 1
    assert default["relevance_audit"]["eligibility_audit"]["include_unverified"] is True
    assert default["relevance_audit"]["eligibility_audit"]["excluded_by_gate"]["maturity"] == 0
    assert mature["relevance_audit"]["eligibility_audit"]["include_unverified"] is False
    assert mature["relevance_audit"]["eligibility_audit"]["excluded_by_gate"]["maturity"] == 1
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("include_unverified,expected_eligible,expected_maturity,expected_context", [
    (False, 2, 2, 1), (True, 3, 0, 2),
])
def test_eligibility_audit_counts_only_first_rejecting_gate_without_changing_results(
        tmp_path, include_unverified, expected_eligible, expected_maturity, expected_context):
    store = ProcessMemoryStore(tmp_path / "records.json")
    base = {"kind": "episode", "maturity": "verified", "text": BODY,
            "source_trace_ids": ["pm_source"], "model_profile": {"family": "model-a"},
            "primary_context": {"project_id": "project-a"}}
    for identity, extra in [
        ("observed", {"kind": "trace", "maturity": "observed"}),
        ("aggregate", {"kind": "capability_observation", "text": "",
                       "verification_evidence": [{"verifier_kind": "automated_test", "status": "passed"}]}),
        ("diagnostic", {"text": "自动捕获失败-修复过程：实际验证：验证结果：pagination"}),
        ("rollout", {"rollout_state": "shadow", "status": "blocked"}),
        ("blocked", {"status": "blocked", "maturity": "observed"}),
        ("immature_context", {"maturity": "observed", "primary_context": {"project_id": "other"}}),
        ("context", {"primary_context": {"project_id": "other"}, "model_profile": {"family": "other"}}),
        ("compatibility", {"model_profile": {"family": "other"}}),
        ("allowed", {}),
    ]:
        store._append(normalize_record({**base, **extra, "process_memory_id": identity}))
    before = store.path.read_bytes()
    page = store.search_page("pagination", include_unverified=include_unverified,
                             primary_context={"project_id": "project-a"},
                             compatibility={"model_family": "model-a"})
    assert page["relevance_audit"]["eligibility_audit"] == {
        "include_unverified": include_unverified,
        "total_record_count": 9,
        "eligible_candidate_count": expected_eligible,
        "excluded_by_gate": {"diagnostic": 1, "rollout": 1, "status_or_drift": 1,
                             "maturity": expected_maturity, "context": expected_context,
                             "compatibility": 1},
    }
    assert page["relevance_audit"]["scope_or_maturity_excluded_count"] == 9 - expected_eligible
    assert {row["process_memory_id"] for row in page["records"]} == (
        {"allowed", "observed"} if include_unverified else {"allowed"})
    assert page["relevance_audit"]["exclusion_reasons"] == {"no_readable_candidate_content": 1}
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("body", [
    {"content": [{"type": "text", "text": BODY}]},
    {"body": {"steps": [{"description": BODY}]}},
    {"repair_actions": [{"procedure": [BODY]}]},
])
def test_nested_readable_body_is_preserved_and_audited_by_production_search(tmp_path, body):
    store = ProcessMemoryStore(tmp_path / "records.json")
    trace = store.record_trajectory({"phase": "recover", **body})
    page = store.search_page("pagination", include_unverified=True)
    assert [row["process_memory_id"] for row in page["records"]] == [trace["process_memory_id"]]
    assert all(page["records"][0][key] == value for key, value in body.items())
    assert page["relevance_audit"]["decisions"][0]["kept"] is True
    assert page["records"][0]["relevance_match_signals"]["content_fields_only"] is True
    assert page["records"][0]["truth_status"] == "unknown"
    assert page["records"][0]["execution_eligible"] is False


@pytest.mark.parametrize("body", [None, 42, False, {}, [], {"text": None},
                                      {"body": [None, 42, {"text": []}]}])
def test_empty_and_malformed_body_do_not_turn_metadata_into_readable_content(body):
    record = {"content": body, "metadata": {"text": BODY}, "profile": {"summary": BODY}}
    relation = classify_candidate("pagination", record)
    assert relation["level"] == "unknown"
    assert relation["reasons"] == ["no_readable_candidate_content"]


def test_user_content_relation_still_ignores_metadata_and_preserves_source_fields():
    rows = [{"id": "body", "text": BODY, "score": 0.12},
            {"id": "metadata", "text": "Potato soup recipe.", "metadata": {"text": BODY}}]
    kept, audit = apply_relevance_policy("pagination", rows)
    assert [row["id"] for row in kept] == ["body"]
    assert kept[0]["text"] == BODY
    assert kept[0]["score"] == 0.12
    assert kept[0]["truth_status"] == "unknown"
    assert kept[0]["execution_eligible"] is False
    assert audit["excluded_count"] == 1
    assert "relevance_level" not in rows[0]
