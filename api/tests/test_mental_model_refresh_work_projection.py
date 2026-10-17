"""Offline refresh work receipts: no database, provider, or runtime state."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from evolving_profile_api.engine import memory_engine as engine_module
from evolving_profile_api.engine.memory_engine import MemoryEngine
from evolving_profile_api.engine.response_models import ReflectResult


@pytest.fixture
def offline_refresh(monkeypatch):
    engine = object.__new__(MemoryEngine)
    cutoff = datetime(2026, 10, 15, 6, tzinfo=UTC)
    watermark = datetime(2026, 10, 15, 5, tzinfo=UTC)
    model = {
        "id": "model",
        "name": "Topic",
        "source_query": "What changed?",
        "content": "Original",
        "trigger": {"mode": "full", "keep_trace": False},
    }
    writes = []
    reflect_inputs = []

    async def authenticate(context):
        return "tenant"

    async def get_model(*args, **kwargs):
        return model.copy()

    async def get_cutoff(*args):
        return cutoff

    async def get_watermark(*args):
        return watermark

    async def update(bank, model_id, **kwargs):
        writes.append(kwargs)
        return {**model, **kwargs}

    async def reflect(**kwargs):
        reflect_inputs.append(kwargs)
        return ReflectResult.model_validate(
            {
                "text": "Updated",
                "based_on": {"observation": [{"id": "f1", "text": "secret fact"}]},
                "usage": {"input_tokens": 111, "output_tokens": 9, "total_tokens": 120},
                "llm_trace": [{"scope": "agent_1", "duration_ms": 10}],
                "tool_trace": [
                    {
                        "tool": "recall",
                        "input": {"query": "secret query"},
                        "output": {"memories": [{"id": "f1", "fact_type": "observation", "text": "secret fact"}]},
                        "duration_ms": 5,
                        "iteration": 1,
                    }
                ],
            }
        )

    monkeypatch.setattr(engine, "_authenticate_tenant", authenticate)
    monkeypatch.setattr(engine, "get_mental_model", get_model)
    monkeypatch.setattr(engine, "_mental_model_refresh_cutoff", get_cutoff)
    monkeypatch.setattr(engine, "_mental_model_processed_watermark", get_watermark)
    monkeypatch.setattr(engine, "update_mental_model", update)
    monkeypatch.setattr(engine, "reflect_async", reflect)
    return SimpleNamespace(
        engine=engine, model=model, writes=writes, reflect_inputs=reflect_inputs, cutoff=cutoff, watermark=watermark
    )


async def test_refresh_without_verbose_trace_persists_bounded_work_receipt(offline_refresh):
    """Removing the receipt would hide actual paid reflect work on normal refreshes."""
    state = offline_refresh
    result = await state.engine.refresh_mental_model("bank", "model", request_context=None)
    receipt = result["reflect_response"]["work"]
    assert receipt["requested_mode"] == "full"
    assert receipt["effective_mode"] == "full"
    assert receipt["reflect_usage"]["input_tokens"] == 111
    assert receipt["reflect_usage"]["output_tokens"] == 9
    assert receipt["reflect_llm_call_count"] == 1
    assert receipt["facts"]["used"] == {"observation": 1}
    assert receipt["window"]["watermark"] == "2026-10-15T05:00:00Z"
    assert receipt["coverage"] == "reflect_only"
    assert "trace" not in result["reflect_response"]
    assert "secret" not in json.dumps(receipt)


async def test_missing_usage_and_traces_remain_unknown(offline_refresh, monkeypatch):
    """Provider omissions must not look like free/zero-call refreshes."""

    async def reflect(**kwargs):
        return ReflectResult(text="Updated", based_on={})

    monkeypatch.setattr(offline_refresh.engine, "reflect_async", reflect)
    result = await offline_refresh.engine.refresh_mental_model("bank", "model", request_context=None)
    receipt = result["reflect_response"]["work"]
    assert receipt["reflect_usage"] is None
    assert receipt["reflect_llm_call_count"] is None


async def test_full_refresh_keeps_running_and_does_not_advance_source_snapshot(offline_refresh):
    """Telemetry cannot turn explicit full refreshes into cache hits or stamp wall time."""
    state = offline_refresh
    await state.engine.refresh_mental_model("bank", "model", request_context=None)
    state.model["source_query"] = "Changed question"
    state.model["trigger"]["response_schema"] = None
    await state.engine.refresh_mental_model("bank", "model", request_context=None)
    assert [call["query"] for call in state.reflect_inputs] == ["What changed?", "Changed question"]
    assert all(call["created_before"] == state.cutoff for call in state.reflect_inputs)
    assert all(write["refresh_watermark"] == state.watermark for write in state.writes)


async def test_operation_receipt_survives_next_model_refresh(offline_refresh, monkeypatch):
    """Model rows keep only the newest run; each operation needs its own projection."""
    state = offline_refresh
    result = await state.engine.refresh_mental_model("bank", "model", request_context=None)
    result["reflect_response"]["work"]["private_tool_payload"] = "secret query"
    operations = []

    class Connection:
        async def execute(self, sql, operation_id, payload):
            operations.append(json.loads(payload))

    @asynccontextmanager
    async def acquire(backend):
        yield Connection()

    async def backend():
        return object()

    monkeypatch.setattr(state.engine, "_get_backend", backend)
    monkeypatch.setattr(engine_module, "acquire_with_retry", acquire)
    await state.engine._write_refresh_outcome_metadata("00000000-0000-0000-0000-000000000001", result)
    assert operations[0]["work"]["reflect_usage"]["input_tokens"] == 111
    assert operations[0]["outcome"] == "content_written"
    assert "secret" not in json.dumps(operations[0]["work"])
