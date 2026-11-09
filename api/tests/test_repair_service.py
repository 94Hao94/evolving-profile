from __future__ import annotations

import pytest

from evolving_profile_api.engine.repair_service import RepairConflictError, RepairService, load_repair_plan, save_repair_plan


def test_diagnose_failed_operation_returns_bounded_retry_plan():
    service = RepairService()

    plan = service.diagnose(
        bank_id="bank-1",
        incident_id="operation:op-1",
        source_id="op-1",
        operation={
            "id": "op-1",
            "task_type": "consolidation",
            "status": "failed",
            "error_message": "request_failed",
        },
        source_fingerprint="source-hash-1",
    )

    assert plan.mode == "auto"
    assert plan.status == "preview_ready"
    assert plan.actions == [{"type": "retry_operation", "operation_id": "op-1", "max_attempts": 1}]
    assert plan.source_fingerprint == "source-hash-1"


def test_diagnose_schema_failure_requires_model_preview():
    service = RepairService()

    plan = service.diagnose(
        bank_id="bank-1",
        incident_id="operation:op-2",
        source_id="op-2",
        operation={
            "id": "op-2",
            "task_type": "batch_retain",
            "status": "failed",
            "error_message": "source_attribution_invalid",
        },
        source_fingerprint="source-hash-2",
    )

    assert plan.mode == "llm"
    assert plan.status == "preview_ready"
    assert plan.risk == "high"
    assert plan.actions[0]["type"] == "dry_run_retain"



def test_diagnose_refresh_failure_gets_domain_repair_action():
    plan = RepairService().diagnose(
        bank_id="bank-1",
        incident_id="operation:op-refresh",
        source_id="op-refresh",
        operation={"id": "op-refresh", "task_type": "refresh_mental_model", "status": "failed", "error_message": "OutputTooLongError"},
        source_fingerprint="hash-refresh",
    )
    assert plan.mode == "llm"
    assert plan.actions == [{"type": "repair_refresh_mental_model", "operation_id": "op-refresh", "max_attempts": 1}]


def test_llm_apply_never_claims_published_success():
    plan = RepairService().diagnose(
        bank_id="bank-1", incident_id="operation:op-llm", source_id="op-llm",
        operation={"id": "op-llm", "task_type": "batch_retain", "status": "failed", "error_message": "schema"},
        source_fingerprint="hash-llm",
    )
    result = RepairService().apply(plan, current_source_fingerprint="hash-llm", confirmed=True)
    assert result.status == "ai_report"
    assert result.apply_receipt == {"status": "ai_report", "reason": "ai_report_only_no_safe_processor"}



def test_llm_apply_accepts_only_a_domain_processor_receipt():
    plan = RepairService().diagnose(
        bank_id="bank-1", incident_id="operation:op-llm-2", source_id="op-llm-2",
        operation={"id": "op-llm-2", "task_type": "refresh_mental_model", "status": "failed"},
        source_fingerprint="hash-llm-2",
    )
    result = RepairService().apply(
        plan,
        current_source_fingerprint="hash-llm-2",
        confirmed=True,
        executor=lambda _action: {"status": "recovered", "operation_id": "op-llm-2"},
    )
    assert result.status == "applied"
    assert result.apply_receipt == {"status": "recovered", "operation_id": "op-llm-2"}


def test_missing_source_creates_manual_review_plan_without_apply_action():
    plan = RepairService().diagnose(
        bank_id="bank-1", incident_id="scenario:pending", source_id=None,
        operation={"task_type": "scenario", "status": "failed", "error_message": "pending_review"},
    )
    assert plan.mode == "llm"
    assert plan.actions == []
    assert plan.root_cause == "source_evidence_unavailable_ai_report"


def test_apply_rejects_changed_source_fingerprint_without_writing():
    service = RepairService()
    plan = service.diagnose(
        bank_id="bank-1",
        incident_id="operation:op-3",
        source_id="op-3",
        operation={"id": "op-3", "task_type": "refresh_mental_model", "status": "failed"},
        source_fingerprint="source-hash-3",
    )

    with pytest.raises(RepairConflictError, match="source_fingerprint_changed"):
        service.apply(plan, current_source_fingerprint="new-source-hash", confirmed=True)

    assert plan.status == "ai_report"


def test_repair_plan_persists_across_service_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOLVING_PROFILE_STATE_ROOT", str(tmp_path))
    plan = RepairService().diagnose(
        bank_id="bank-1", incident_id="operation:op-4", source_id="op-4",
        operation={"id": "op-4", "task_type": "consolidation", "status": "failed"},
        source_fingerprint="hash-4",
    )
    save_repair_plan(plan)
    loaded = load_repair_plan(plan.repair_id)
    assert loaded is not None
    assert loaded.source_fingerprint == "hash-4"
