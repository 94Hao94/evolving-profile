"""The metadata-only operation list retains explicit backend batch lineage."""
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from evolving_profile_api.api.http import OperationResponse
from evolving_profile_api.engine.memory_engine import MemoryEngine


@pytest.mark.asyncio
async def test_list_projects_parent_id_without_exposing_metadata(monkeypatch):
    at = datetime(2026, 10, 13, tzinfo=timezone.utc)
    parent = "67aa2af8-0000-4000-8000-000000000000"
    child = "31c9145f-0000-4000-8000-000000000000"

    class Connection:
        parse_json = staticmethod(json.loads)

        async def fetchrow(self, query, *args):
            return {"total": 1}

        async def fetch(self, query, *args):
            assert args[:2] == ("bank-a", "failed")
            return [{"operation_id": child, "operation_type": "retain", "created_at": at,
                     "updated_at": at, "status": "failed", "error_message": None,
                     "result_metadata": json.dumps({"parent_operation_id": parent, "content": "PRIVATE"}),
                     "retry_count": 0, "next_retry_at": None}]

    @asynccontextmanager
    async def acquire(_backend):
        yield Connection()

    monkeypatch.setattr("evolving_profile_api.engine.memory_engine.acquire_with_retry", acquire)
    engine = MemoryEngine.__new__(MemoryEngine)
    engine._authenticate_tenant = AsyncMock()
    engine._operation_validator = None
    engine._get_backend = AsyncMock(return_value=object())
    listed = await engine.list_operations("bank-a", status="failed", request_context=object())
    payload = OperationResponse(**listed["operations"][0]).model_dump()
    assert payload.get("parent_operation_id") == parent
    assert "PRIVATE" not in json.dumps(payload)
    assert "result_metadata" not in payload
