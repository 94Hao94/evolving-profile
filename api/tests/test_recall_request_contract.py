"""Compatibility contract for EP host-provenance fields on HTTP recall."""

import pytest
from pydantic import ValidationError

from evolving_profile_api.api.http import RecallRequest


def test_recall_accepts_bounded_ep_prompt_provenance_fields() -> None:
    request = RecallRequest(
        query="deployment status",
        raw_user_prompt="继续检查部署状态",
        full_prompt="前文任务：检查 API 与宿主回执\n本轮问题：继续检查部署状态",
        full_prompt_source="agent_contract",
    )

    assert request.raw_user_prompt == "继续检查部署状态"
    assert request.full_prompt_source == "agent_contract"
    assert request.model_dump(mode="json")["full_prompt"].startswith("前文任务")


@pytest.mark.parametrize(
    ("field", "limit"),
    [("raw_user_prompt", 48000), ("full_prompt", 48000), ("full_prompt_source", 160)],
)
def test_recall_rejects_oversized_ep_prompt_provenance(field: str, limit: int) -> None:
    with pytest.raises(ValidationError):
        RecallRequest(query="status", **{field: "x" * (limit + 1)})

