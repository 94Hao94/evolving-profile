from source_of_truth_audit import audit


def test_live_source_of_truth_audit_is_consistent():
    result = audit()
    assert result["schema"] == "evolving-profile.source-of-truth-audit.v1"
    assert result["ok"] is True
    assert all(item["ok"] for item in result["checks"])
