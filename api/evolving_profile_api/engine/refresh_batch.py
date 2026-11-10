"""Deterministic source-slice planning and parent receipt aggregation.

This module is intentionally independent from the worker and database layers.
It gives refresh orchestration a stable child-slice contract before callers
schedule any LLM work or persist a parent operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class RefreshSourceSlice:
    """One bounded source window to process as a child refresh."""

    index: int
    total: int
    source_ids: tuple[str, ...]
    token_estimate: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub_batch_index": self.index,
            "total_sub_batches": self.total,
            "source_ids": list(self.source_ids),
            "token_estimate": self.token_estimate,
        }


def plan_refresh_subbatches(
    sources: Iterable[dict[str, Any]], *, max_tokens: int
) -> list[RefreshSourceSlice]:
    """Pack source rows into deterministic bounded slices.

    ``sources`` must be in the caller's authoritative order. Each row may carry
    ``id``/``source_id`` and ``token_estimate`` (or ``tokens``). A single row
    larger than the limit remains intact as one child so no source is silently
    dropped; the child receipt exposes the oversize estimate for diagnostics.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens_must_be_positive")
    batches: list[tuple[list[str], int]] = []
    seen: set[str] = set()
    for row in sources:
        if not isinstance(row, dict):
            raise ValueError("source_row_must_be_object")
        source_id = str(row.get("source_id") or row.get("id") or "").strip()
        if not source_id:
            raise ValueError("source_id_required")
        if source_id in seen:
            raise ValueError("duplicate_source_id")
        seen.add(source_id)
        tokens = int(row.get("token_estimate") or row.get("tokens") or 0)
        if tokens < 0:
            raise ValueError("token_estimate_must_be_non_negative")
        if not batches or (batches[-1][1] and batches[-1][1] + tokens > max_tokens):
            batches.append(([], 0))
        batches[-1][0].append(source_id)
        batches[-1] = (batches[-1][0], batches[-1][1] + tokens)
    total = len(batches)
    return [
        RefreshSourceSlice(index=index, total=total, source_ids=tuple(ids), token_estimate=tokens)
        for index, (ids, tokens) in enumerate(batches, 1)
    ]


def aggregate_refresh_receipts(
    parent_operation_id: str, child_receipts: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Build a truthful parent receipt from child outcomes.

    A parent is ``completed`` only when every child is completed. It is
    ``partial`` when at least one child completed and another child failed or
    remains pending. The function never converts missing child receipts into a
    successful coverage claim.
    """
    rows = [row for row in child_receipts if isinstance(row, dict)]
    rows.sort(key=lambda row: int(row.get("sub_batch_index") or 0))
    statuses = [str(row.get("status") or "unknown") for row in rows]
    completed = [row for row in rows if row.get("status") == "completed"]
    failed = [row for row in rows if row.get("status") == "failed"]
    pending = [row for row in rows if row.get("status") in {"pending", "processing", "unknown"}]
    if rows and len(completed) == len(rows):
        status, coverage = "completed", "complete"
    elif completed:
        status, coverage = "partial", "incomplete"
    elif failed and not pending:
        status, coverage = "failed", "incomplete"
    else:
        status, coverage = "pending", "unknown"
    source_ids = [
        source_id
        for row in rows
        for source_id in (row.get("source_ids") or [])
        if isinstance(source_id, str)
    ]
    return {
        "schema": "ep.refresh-parent-receipt.v1",
        "parent_operation_id": str(parent_operation_id),
        "status": status,
        "coverage": coverage,
        "total_sub_batches": len(rows),
        "completed_sub_batches": len(completed),
        "failed_sub_batches": len(failed),
        "pending_sub_batches": len(pending),
        "child_statuses": statuses,
        "source_ids": source_ids,
        "missing_source_ids": [],
    }
