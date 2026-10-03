"""Read-only historical process candidate scanner.

It deliberately never writes ProcessMemoryStore. Candidates require source-read and
independent verification before promotion.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

SIGNALS = ("error", "failed", "failure", "retry", "重试", "失败", "修复", "回退", "验证", "测试")


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def scan_history_lines(lines: Iterable[str], *, cutoff: datetime) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    active_session = ""
    for raw in lines:
        try:
            row = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict):
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if row.get("type") == "session_meta":
            active_session = str(payload.get("session_id") or payload.get("id") or "").strip()
        at = _time(row.get("timestamp") or payload.get("timestamp") or row.get("created_at") or row.get("time"))
        if at is None or at >= cutoff.astimezone(timezone.utc):
            continue
        session_id = str(row.get("session_id") or row.get("session") or payload.get("session_id") or active_session).strip()
        if not session_id:
            continue
        content = payload.get("content") if payload else row.get("content")
        if isinstance(content, list):
            content = " ".join(str(item.get("text") if isinstance(item, dict) else item) for item in content)
        text = str(content or payload.get("text") or row.get("text") or row.get("output") or "")
        tool = row.get("name") or row.get("tool") or payload.get("name") or payload.get("call_id") or (payload.get("type") if "call" in str(payload.get("type")) else None)
        role = row.get("role") or payload.get("role")
        if role not in {"user", "assistant", "tool"} and not tool:
            continue
        if text or tool:
            groups[session_id].append({"role": role, "text": text, "at": at.isoformat(), "tool": tool})
    candidates = []
    for session_id, rows in groups.items():
        signal_rows = [row for row in rows if any(signal in row["text"].lower() for signal in SIGNALS)]
        tool_rows = [row for row in rows if row.get("tool") or row.get("role") == "tool"]
        if len(signal_rows) < 1 or not tool_rows:
            continue
        candidates.append({
            "schema": "evolving-profile.historical-process-candidate.v1",
            "session_id": session_id,
            "status": "candidate_read_only",
            "promotion_allowed": False,
            "source_count": len(rows),
            "signal_count": len(signal_rows),
            "tool_event_count": len(tool_rows),
            "signal_types": sorted({signal for signal in SIGNALS if any(signal in row["text"].lower() for row in signal_rows)}),
            "source_excerpt": [row["text"][:240] for row in signal_rows[:5]],
            "cutoff": cutoff.astimezone(timezone.utc).isoformat(),
            "next_step": "read_source_then_independent_verifier",
        })
    return sorted(candidates, key=lambda row: row["session_id"])


def paginate_candidates(candidates: list[dict[str, Any]], *, offset: int = 0, limit: int = 50) -> dict[str, Any]:
    offset = max(0, int(offset))
    limit = max(1, min(int(limit), 200))
    items = candidates[offset:offset + limit]
    next_offset = offset + limit if offset + limit < len(candidates) else None
    return {"offset": offset, "limit": limit, "returned_count": len(items), "total": len(candidates), "next_offset": next_offset, "items": items}


def candidate_quality_stats(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "candidate_count": len(candidates),
        "high_signal_count": sum(1 for row in candidates if int(row.get("signal_count") or 0) >= 2),
        "with_tool_events_count": sum(1 for row in candidates if int(row.get("tool_event_count") or 0) > 0),
        "promotion_allowed_count": sum(1 for row in candidates if row.get("promotion_allowed") is True),
        "read_only_count": sum(1 for row in candidates if row.get("status") == "candidate_read_only"),
    }
