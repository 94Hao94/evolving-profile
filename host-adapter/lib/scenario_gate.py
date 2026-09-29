"""Deterministic gate for expanding Project/Session Scenario Summaries.

The gate never invents evidence. It decides only whether a candidate result
has an explanation gap that warrants a bounded summary expansion.
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from lib.context_associations import project_key


def _route_hint(prompt: str, gaps: list[str], rows: list[dict], project_count: int, session_count: int,
                current_context_sufficient: bool) -> dict:
    """Choose the next evidence surface without treating summaries as facts."""
    if current_context_sufficient:
        return {"recommended_route": "none", "recommended_tier": None, "raw_read_trigger": None}
    if not rows:
        return {"recommended_route": "search_scenario_summary", "recommended_tier": None,
                "raw_read_trigger": "当前没有可绑定的 Session/Project 候选，先重新做情景导航"}
    text = " ".join([str(prompt or ""), *gaps]).lower()
    exact = any(token in text for token in (
        "原话", "逐字", "原始", "全文", "原文", "具体对话", "谁说", "当时说", "争论", "聊天记录",
        "原始 session", "原始会话", "原始 project", "原始项目",
    ))
    project_scope = any(token in text for token in (
        "整个项目", "项目全程", "项目演变", "跨会话", "所有会话", "project 全部", "project全程",
    ))
    factual = any(token in text for token in (
        "金额", "预算", "时间", "日期", "人物", "角色", "版本", "数字", "具体事实", "来源",
        "状态", "是否完成", "谁负责",
    ))
    if exact and project_scope:
        return {"recommended_route": "audit_project_sessions", "recommended_tier": None,
                "raw_read_trigger": "用户明确需要 Project 下多个 Session 的原始过程或逐字内容"}
    if exact:
        return {"recommended_route": "audit_session", "recommended_tier": None,
                "raw_read_trigger": "用户明确需要原始 Session 对话、原话或完整过程"}
    if factual:
        has_memory_id = any(str(row.get("canonical_memory_id") or row.get("memory_id") or row.get("id") or "").strip()
                            for row in rows)
        return {"recommended_route": "read_source" if has_memory_id else "research_then_read_source",
                "recommended_tier": None,
                "raw_read_trigger": "问题需要同一对象和版本的原始事实证据"}
    if project_count > 1 or session_count > 1 or len(gaps) >= 2:
        return {"recommended_route": "scenario_standard", "recommended_tier": "standard",
                "raw_read_trigger": None}
    return {"recommended_route": "scenario_compact", "recommended_tier": "compact", "raw_read_trigger": None}


def _deduplicate(candidates):
    result = OrderedDict()
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("canonical_memory_id") or item.get("id") or "").strip()
        if key and key not in result:
            result[key] = item
    return list(result.values())


def decide_scenario_summary(prompt: str, candidates=None, current_context_sufficient=False, *,
                            unresolved_slots=None, max_hops=1):
    """Select an initial read only after the Agent names an evidence gap."""
    rows = _deduplicate(candidates)
    projects = defaultdict(list)
    sessions = defaultdict(list)
    for row in rows:
        metadata = row.get("metadata") or {}
        project = str(row.get("project_key") or metadata.get("project_key") or
                      project_key(metadata.get("project") or metadata.get("cwd")) or "").strip()
        session_values = row.get("session_ids") or metadata.get("session_ids") or metadata.get("session_id") or []
        if isinstance(session_values, str):
            session_values = [v.strip() for v in session_values.split(",") if v.strip()]
        if project:
            projects[project].append(row)
        for session in session_values:
            sessions[str(session)].append(row)

    gaps = [str(value).strip() for value in unresolved_slots or [] if str(value).strip()][:8]
    if not rows:
        decision, reasons = "none", ["no_candidates"]
    elif current_context_sufficient:
        decision, reasons = "none", ["current_context_sufficient"]
    elif not projects and not sessions:
        decision, reasons = "unavailable_no_scope_link", ["candidate_scope_not_indexed"]
    elif not gaps:
        decision, reasons = "agent_decides", ["evidence_gap_not_supplied"]
    else:
        decision, reasons = "compact", ["explicit_evidence_gap"]
    route = _route_hint(prompt, gaps, rows, len(projects), len(sessions), current_context_sufficient)
    return {
        "decision": decision,
        "reason_codes": list(dict.fromkeys(reasons)),
        "unresolved_slots": gaps,
        "project_count": len(projects),
        "session_count": len(sessions),
        "candidate_count": len(candidates or []),
        "deduplicated_count": len(rows),
        "project_groups": {key: len(value) for key, value in projects.items()},
        "session_groups": {key: len(value) for key, value in sessions.items()},
        "max_hops": max(0, min(2, int(max_hops))),
        **route,
        "evidence_role": "scenario_explanation_only",
        "boundary": "Decision is not fact verification. Summary tiers explain scope; read_source verifies Bank facts; audit_session/audit_project_sessions reads bounded raw conversation only when the prompt requires original wording or process.",
    }
