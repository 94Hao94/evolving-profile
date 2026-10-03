import pytest
import json
from pathlib import Path

from lib.process_memory_evaluation import evaluate_ab, transfer_gate, build_revalidation_queue


def test_ab_evaluation_reports_improvement_and_cost():
    result = evaluate_ab(
        baseline=[{"failed": True, "recovery_seconds": 20, "tool_calls": 8, "tokens": 1000}],
        memory=[{"failed": False, "recovery_seconds": 10, "tool_calls": 5, "tokens": 1200}],
    )
    assert result["failure_rate_delta"] == -1.0
    assert result["recovery_seconds_delta"] == -10.0
    assert result["tool_calls_delta"] == -3.0
    assert result["context_cost_delta"] == 200.0


def test_transfer_gate_rejects_negative_transfer_and_small_samples():
    assert transfer_gate({"sample_count": 2, "negative_transfer_rate": 0.0})["status"] == "candidate"
    assert transfer_gate({"sample_count": 10, "negative_transfer_rate": 0.2})["status"] == "blocked"
    assert transfer_gate({"sample_count": 10, "verified_receipt_pairs": 10, "negative_transfer_rate": 0.0, "improvement_rate": 0.3})["status"] == "verified"


def test_revalidation_queue_excludes_stable_records():
    rows = build_revalidation_queue([
        {"process_memory_id": "a", "drift_status": "stable"},
        {"process_memory_id": "b", "drift_status": "revalidation_required"},
        {"process_memory_id": "c", "drift_status": "deprecated"},
    ])
    assert [row["process_memory_id"] for row in rows] == ["b", "c"]


def test_ab_evaluation_requires_equal_pair_counts():
    with pytest.raises(ValueError, match="evaluation_pair_count_mismatch"):
        evaluate_ab([], [{"failed": False}])


def test_missing_outcomes_are_not_counted_as_success():
    with pytest.raises(ValueError, match="evaluation_outcome_missing"):
        evaluate_ab([{}], [{}])


def test_pair_identity_cannot_mix_different_tasks():
    with pytest.raises(ValueError, match="evaluation_task_mismatch"):
        evaluate_ab([{"task_id": "a", "failed": False}], [{"task_id": "b", "failed": False}])


def test_evaluation_derives_negative_transfer_from_paired_outcomes():
    result = evaluate_ab([{"failed": False}, {"failed": True}], [{"failed": True}, {"failed": False}])
    assert result["negative_transfer_rate"] == 0.5
    assert result["improvement_rate"] == 0.5
    assert result["verified_receipt_pairs"] == 0


def test_reported_metrics_alone_cannot_verify_transfer():
    assert transfer_gate({"sample_count": 100, "improvement_rate": 1.0})["status"] == "candidate"


def test_evaluation_registry_keeps_real_receipts_and_historical_mode_read_only():
    registry = json.loads(Path(__file__).parents[1].joinpath('docs/EP5.0-EVALUATION-REGISTRY.json').read_text())
    assert registry['policy']['historical_mode'] == 'read_only_candidate'
    assert len(registry['slices']) >= 5
    assert 'verifier_status' in registry['required_receipt_fields']
