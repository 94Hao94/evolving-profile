from evolving_profile_api.api.http import RepairApplyRequest, RepairDiagnoseRequest, RepairResponse


def test_repair_request_and_response_contract_is_preview_first():
    request = RepairDiagnoseRequest(
        incident_id="operation:op-1",
        source_id="op-1",
        source_fingerprint="hash-1",
        operation={"status": "failed", "task_type": "retain"},
    )
    assert request.incident_id == "operation:op-1"
    assert RepairApplyRequest().confirmed is False

    response = RepairResponse(
        repair_id="repair-1",
        bank_id="bank-1",
        incident_id=request.incident_id,
        source_id=request.source_id,
        mode="llm",
        status="preview_ready",
        root_cause="schema",
        risk="high",
        actions=[],
        evidence=[],
        source_fingerprint=request.source_fingerprint,
        regression_plan=["source_fingerprint"],
    )
    assert response.status == "preview_ready"
