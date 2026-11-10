import pytest

from evolving_profile_api.engine.mental_model_refresh import split_refresh_batches


def test_split_refresh_batches_bounds_each_batch_and_preserves_order():
    items = ["a", "b", "c", "d", "e"]

    assert split_refresh_batches(items, max_batch_size=2) == [["a", "b"], ["c", "d"], ["e"]]


def test_split_refresh_batches_rejects_non_positive_batch_size():
    with pytest.raises(ValueError):
        split_refresh_batches(["a"], max_batch_size=0)
