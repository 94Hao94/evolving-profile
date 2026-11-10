import pytest

from evolving_profile_api.engine.refresh_batch import aggregate_refresh_receipts, plan_refresh_subbatches
from evolving_profile_api.engine.operation_metadata import RefreshChildMetadata, RefreshParentMetadata


def test_plan_refresh_subbatches_is_deterministic_and_bounded():
    rows = [{"id": f"s{i}", "token_estimate": tokens} for i, tokens in enumerate([4, 3, 6, 2], 1)]
    slices = plan_refresh_subbatches(rows, max_tokens=8)
    assert [slice.source_ids for slice in slices] == [("s1", "s2"), ("s3", "s4")]
    assert [slice.token_estimate for slice in slices] == [7, 8]
    assert [slice.to_dict()["total_sub_batches"] for slice in slices] == [2, 2]


def test_oversize_single_source_is_preserved_for_child_diagnostics():
    slices = plan_refresh_subbatches([{"source_id": "large", "tokens": 99}], max_tokens=10)
    assert slices[0].source_ids == ("large",)
    assert slices[0].token_estimate == 99


def test_duplicate_or_invalid_sources_fail_closed():
    with pytest.raises(ValueError, match="duplicate_source_id"):
        plan_refresh_subbatches([{"id": "a"}, {"id": "a"}], max_tokens=10)
    with pytest.raises(ValueError, match="source_id_required"):
        plan_refresh_subbatches([{"token_estimate": 1}], max_tokens=10)


def test_parent_receipt_distinguishes_complete_partial_and_failed():
    complete = aggregate_refresh_receipts("p", [
        {"sub_batch_index": 1, "status": "completed", "source_ids": ["a"]},
        {"sub_batch_index": 2, "status": "completed", "source_ids": ["b"]},
    ])
    partial = aggregate_refresh_receipts("p", [
        {"sub_batch_index": 1, "status": "completed", "source_ids": ["a"]},
        {"sub_batch_index": 2, "status": "failed", "source_ids": ["b"]},
    ])
    failed = aggregate_refresh_receipts("p", [
        {"sub_batch_index": 1, "status": "failed", "source_ids": ["a"]},
    ])
    assert (complete["status"], complete["coverage"]) == ("completed", "complete")
    assert (partial["status"], partial["coverage"]) == ("partial", "incomplete")
    assert (failed["status"], failed["coverage"]) == ("failed", "incomplete")


def test_refresh_parent_and_child_metadata_are_machine_readable():
    parent = RefreshParentMetadata("mm-1", 3, 120, 2).to_dict()
    child = RefreshChildMetadata("parent-1", 1, 2, ["s1", "s2"], 80).to_dict()
    assert parent["schema"] == "ep.refresh-parent-metadata.v1"
    assert parent["is_parent"] is True
    assert child["schema"] == "ep.refresh-child-metadata.v1"
    assert child["source_ids"] == ["s1", "s2"]
