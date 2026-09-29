"""Evidence-preserving Session/Project context summaries.

Context is a navigation and disambiguation layer, not a Bank fact lane.  The
module is deliberately deterministic: model-generated summaries may be used
as seeds later, but this layer only bounds, groups, and records provenance.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
import re
import hashlib


BUDGETS = {
    "session": {
        "compact": {"max_chars": 500, "max_tokens": 400},
        "standard": {"max_chars": 1200, "max_tokens": 900},
        "full": {"max_chars": 4000, "max_tokens": 3000},
    },
    "project": {
        "compact": {"max_chars": 800, "max_tokens": 600},
        "standard": {"max_chars": 3000, "max_tokens": 2000},
        "full": {"max_chars": 8000, "max_tokens": 5000},
    },
}

SCHEMA = "evolving-profile.context-index.v1"


def estimate_tokens(text: str) -> int:
    """Conservative local estimate used only for budget enforcement.

    It intentionally overestimates mixed text rather than depending on a
    provider tokenizer that may change between GPT-6 Luna and other hosts.
    """
    value = str(text or "")
    return max(0, math.ceil(len(value) / 2))


def _clean(text: str) -> str:
    lines = []
    for raw in str(text or "").replace("\r\n", "\n").splitlines():
        line = " ".join(raw.split())
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def _clip_chars(text: str, maximum: int) -> tuple[str, bool]:
    value = str(text or "")
    if len(value) <= maximum:
        return value, False
    clipped = value[: max(0, maximum - 1)].rstrip() + "…"
    return clipped, True


def bounded_summary(text: str, context_type: str, tier: str) -> tuple[str, dict]:
    if context_type not in BUDGETS or tier not in BUDGETS[context_type]:
        raise ValueError("invalid_context_budget")
    limits = BUDGETS[context_type][tier]
    value = _clean(text)
    value, clipped = _clip_chars(value, int(limits["max_chars"]))
    # Character and token limits are independent safety rails.  Re-clip until
    # both pass, preserving a visible truncation marker when possible.
    while estimate_tokens(value) > int(limits["max_tokens"]) and value:
        target = max(1, int(limits["max_tokens"]) * 2 - 1)
        value, more_clipped = _clip_chars(value, target)
        clipped = clipped or more_clipped
    return value, {
        "context_type": context_type,
        "tier": tier,
        "max_chars": int(limits["max_chars"]),
        "max_tokens": int(limits["max_tokens"]),
        "chars": len(value),
        "estimated_tokens": estimate_tokens(value),
        "truncated": clipped,
    }


def _unique(values: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _summary_layers(text: str, context_type: str) -> tuple[dict, dict]:
    summaries = {}
    receipts = {}
    for tier in ("compact", "standard", "full"):
        summaries[tier], receipts[tier] = bounded_summary(text, context_type, tier)
    return summaries, receipts


def reproject_context_row(row: dict) -> dict:
    """Bound an existing seed without claiming semantic review or lost coverage."""
    context_type = str(row.get("context_type") or "")
    seed = str((row.get("summary") or {}).get("full") or (row.get("summary") or {}).get("standard") or "")
    if context_type not in BUDGETS or not seed:
        raise ValueError("context_row_missing_seed")
    prior_budget = row.get("summary_budget") or {}
    inherited_truncation = bool((prior_budget.get("full") or {}).get("truncated")) or seed.endswith("…")
    summaries, receipts = _summary_layers(seed, context_type)
    for tier in receipts:
        receipts[tier]["truncated"] = receipts[tier]["truncated"] or inherited_truncation
        receipts[tier]["source_already_truncated"] = inherited_truncation
    return {
        **row,
        "summary": summaries,
        "summary_budget": receipts,
        "status": "deterministic_projection_unreviewed",
        "processing_method": "deterministic_source_projection",
        "summary_model": None,
        "review_model": None,
    }


def build_session_context(session_id: str, project_key: str, source_ids: Iterable[str],
                          seed_text: str, updated_at: str | None = None) -> dict:
    """Create a reviewable Session Context from a rollout/summary seed."""
    session_id = str(session_id or "").strip()
    if not session_id:
        raise ValueError("session_id_required")
    updated = str(updated_at or datetime.now(timezone.utc).isoformat())
    summaries, budget = _summary_layers(seed_text, "session")
    return {
        "context_id": "session:" + session_id,
        "context_type": "session",
        "session_id": session_id,
        "project_key": str(project_key or "").strip(),
        "summary": summaries,
        "summary_budget": budget,
        "source_ids": _unique(source_ids),
        "updated_at": updated,
        "status": "seeded_pending_review",
        "summary_model": "gpt-6-luna-light-reasoning_seed_contract",
        "review_model": "gpt-6-sol-medium-reasoning_on_sample_or_conflict",
        "evidence_role": "context_navigation_only",
    }


def build_project_context(project_key: str, sessions: Iterable[dict], updated_at: str | None = None) -> dict:
    """Aggregate only sessions explicitly belonging to ``project_key``."""
    project_key = str(project_key or "").strip()
    eligible = [row for row in sessions if isinstance(row, dict) and str(row.get("project_key") or "") == project_key]
    eligible.sort(key=lambda row: (str(row.get("updated_at") or ""), str(row.get("session_id") or "")))
    combined = "\n".join(
        f"[{row.get('session_id')}] {part}"
        for row in eligible
        if (part := str(row.get("summary", {}).get("standard") or "").strip())
    )
    summaries, budget = _summary_layers(combined, "project")
    return {
        "context_id": "project:" + project_key,
        "context_type": "project",
        "project_key": project_key,
        "identity_status": "unverified_workspace_bucket",
        "summary": summaries,
        "summary_budget": budget,
        "session_ids": _unique(row.get("session_id") for row in eligible),
        "source_ids": _unique(source for row in eligible for source in row.get("source_ids") or []),
        "updated_at": str(updated_at or datetime.now(timezone.utc).isoformat()),
        "status": "seeded_pending_review" if eligible else "unknown_no_session_context",
        "summary_model": "gpt-6-luna-light-reasoning_seed_contract",
        "review_model": "gpt-6-sol-medium-reasoning_on_sample_or_conflict",
        "evidence_role": "context_navigation_only",
    }


def write_context_index(path: str | os.PathLike, sessions: Iterable[dict], projects: Iterable[dict]) -> dict:
    """Atomically write the derived index; raw source files are untouched."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sessions": list(sessions),
        "projects": list(projects),
        "source_of_truth": "codex_rollout_or_ep_session_index",
        "evidence_role": "context_navigation_only",
    }
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return {"ok": True, "path": str(target), "session_count": len(payload["sessions"]), "project_count": len(payload["projects"])}


def read_context_index(path: str | os.PathLike) -> dict:
    target = Path(path).expanduser()
    if not target.is_file():
        return {"schema": SCHEMA, "status": "unavailable_missing_index", "sessions": [], "projects": []}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": SCHEMA, "status": "unavailable_invalid_index", "sessions": [], "projects": []}
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return {"schema": SCHEMA, "status": "unavailable_schema_mismatch", "sessions": [], "projects": []}
    payload.setdefault("status", "ready")
    payload.setdefault("sessions", [])
    payload.setdefault("projects", [])
    return payload


def context_navigation(session_id: str, cwd: str, index_path: str | os.PathLike) -> str:
    """Return a small, explicitly non-factual L0 navigation block."""
    index = read_context_index(index_path)
    project_key = hashlib.sha256(str(cwd or "").encode("utf-8")).hexdigest()[:16] if cwd else ""
    session = next((row for row in index.get("sessions", [])
                    if str(row.get("session_id") or "") == str(session_id or "")), None)
    project = next((row for row in index.get("projects", [])
                    if project_key and str(row.get("project_key") or "") == project_key), None)
    payload = {
        "status": index.get("status") or "unavailable",
        "session": {
            "context_id": session.get("context_id") if session else None,
            "summary": (session.get("summary") or {}).get("compact") if session else None,
            "source_ids": session.get("source_ids", []) if session else [],
            "state": session.get("status") if session else "not_found",
        },
        "project": {
            "context_id": project.get("context_id") if project else None,
            "summary": (project.get("summary") or {}).get("compact") if project else None,
            "source_ids": project.get("source_ids", []) if project else [],
            "state": project.get("status") if project else "not_found",
        },
        "boundary": "navigation_only_not_bank_fact; expand_with_read_context_summary_when_needed",
    }
    return "<evolving_profile_context_navigation>\n" + json.dumps(payload, ensure_ascii=False) + "\n</evolving_profile_context_navigation>"


def discover_codex_rollout_seeds(memory_root: str | os.PathLike) -> list[dict]:
    """Parse native Codex rollout-summary metadata without treating it as fact.

    Each markdown file is one bounded seed.  The original summary path and
    thread ID remain provenance; no Bank record is created here.
    """
    root = Path(memory_root).expanduser()
    if not root.is_dir():
        return []
    rows = []
    for path in sorted((root / "rollout_summaries").glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        headers = {}
        for line in text.splitlines()[:20]:
            match = re.match(r"^(thread_id|updated_at|rollout_path|cwd):\s*(.+?)\s*$", line)
            if match:
                headers[match.group(1)] = match.group(2)
        thread_id = headers.get("thread_id") or path.stem
        cwd = headers.get("cwd", "")
        project_key = hashlib.sha256(cwd.encode("utf-8")).hexdigest()[:16] if cwd else ""
        body = text.split("\n\n", 1)[1] if "\n\n" in text else text
        rows.append({
            "session_id": thread_id,
            "project_key": project_key,
            "source_ids": [str(path)],
            "seed_text": _clean(body),
            "updated_at": headers.get("updated_at"),
            "rollout_path": headers.get("rollout_path"),
            "cwd": cwd,
        })
    return rows


def build_index_from_codex_memory(memory_root: str | os.PathLike) -> tuple[list[dict], list[dict]]:
    """Build review-pending Context rows from Codex native summaries."""
    sessions = [build_session_context(
        row["session_id"], row["project_key"], row["source_ids"], row["seed_text"], row.get("updated_at")
    ) for row in discover_codex_rollout_seeds(memory_root)]
    project_keys = _unique(row.get("project_key") for row in sessions)
    projects = [build_project_context(key, sessions) for key in project_keys if key]
    return sessions, projects
