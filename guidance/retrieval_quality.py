"""Bounded retrieval contracts and evidence-quality escalation decisions.

The module is deliberately pure. It projects metadata already returned by the
Bank and decides whether a broader read is justified; it never writes memory,
claims model attention, or treats a candidate as an injected fact.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any


_BROAD_MARKERS = ("全部", "所有", "完整", "盘点", "梳理", "时间线", "演变", "关系", "关联闭包", "多跳")
_EVIDENCE_MARKERS = ("来源", "证据", "原文", "核对", "审计", "事实", "经历", "实体", "历史")
_CONFLICT_MARKERS = ("冲突", "矛盾", "哪个为准", "到底", "取代", "替代", "过时", "失效")


def _bounded_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def _month_bounds(query: str) -> dict[str, str | None]:
    matches = [(int(y), int(m)) for y, m in re.findall(r"(20\d{2})\s*年\s*(1[0-2]|0?[1-9])\s*月", query)]
    range_match = re.search(r"(20\d{2})\s*年\s*(1[0-2]|0?[1-9])\s*月\s*(?:到|至|[-~～])\s*(1[0-2]|0?[1-9])\s*月", query)
    if range_match:
        matches.extend([
            (int(range_match.group(1)), int(range_match.group(2))),
            (int(range_match.group(1)), int(range_match.group(3))),
        ])
    if not matches:
        return {"start": None, "end": None, "source": "not_explicit"}
    first, last = min(matches), max(matches)
    start = dt.date(first[0], first[1], 1)
    if last[1] == 12:
        next_month = dt.date(last[0] + 1, 1, 1)
    else:
        next_month = dt.date(last[0], last[1] + 1, 1)
    end = next_month - dt.timedelta(days=1)
    return {"start": start.isoformat(), "end": end.isoformat(), "source": "explicit_month_range"}


def _subjects(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw = list((plan.get("contextual_intent") or {}).get("resolved_subjects") or [])
    output: list[dict[str, Any]] = []
    for index, value in enumerate(raw):
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("label") or value.get("id") or "").strip()
            subject_id = str(value.get("id") or name or f"subject:{index}")
            aliases = [str(item).strip() for item in value.get("aliases") or [] if str(item).strip()]
        else:
            name = str(value).strip()
            subject_id = name
            aliases = []
        if name and subject_id:
            output.append({"id": subject_id, "name": name, "aliases": list(dict.fromkeys(aliases))})
    if output:
        return output
    # Direct MCP/Controller calls may not carry the adapter's resolved-subject
    # envelope. Recover only conservative relationship/name anchors from the
    # user query; this is a query hint, never identity verification.
    query = str(plan.get("query") or "")
    for name in ("老婆", "妻子", "优优", "女儿", "儿子", "孩子"):
        if name in query:
            output.append({"id": f"subject:{name}", "name": name, "aliases": []})
    return output


def build_retrieval_contract(
    query: str,
    plan: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the explicit, serializable contract for one Bank query."""
    plan = dict(plan or {})
    config = dict(config or {})
    plan["query"] = str(query or "")
    project = dict(plan.get("project_state") or {})
    required = list(dict.fromkeys(str(value) for value in plan.get("coverage_dimensions") or [] if str(value)))
    shape = str(plan.get("primary_shape") or "point")
    graph_required = bool(
        (plan.get("relation_closure") or {}).get("required")
        or (plan.get("graph_route") or {}).get("enabled")
        or any(marker in query for marker in ("关系", "关联", "别名", "上下游", "因果链", "多跳"))
    )
    graph_budget = {
        "max_hops": _bounded_int(config.get("graphMaxHops"), 2, 1, 3),
        "max_nodes": _bounded_int(config.get("graphMaxNodes"), 80, 10, 120),
        "max_candidates": _bounded_int(config.get("graphMaxCandidates"), 10, 1, 20),
        "max_tokens": _bounded_int(config.get("graphMaxTokens"), 1200, 200, 4000),
        "latency_ms": _bounded_int(config.get("graphLatencyMs"), 6000, 500, 12000),
        "max_seed_queries": _bounded_int(config.get("graphMaxSeedQueries"), 3, 1, 5),
    }
    return {
        "schema": "evolving-profile.retrieval-contract.v1",
        "query": str(query or ""),
        "shape": shape,
        "subjects": _subjects(plan),
        "temporal": _month_bounds(str(query or "")),
        "task": {
            "project_key": project.get("project_key") or project.get("project") or plan.get("project_key"),
            "task_id": project.get("task_id") or plan.get("task_id"),
            "topic": project.get("topic") or plan.get("topic"),
        },
        "evidence": {
            "required": bool(required or any(marker in str(query) for marker in _EVIDENCE_MARKERS)),
            "coverage_dimensions": required,
            "minimum_sources": 2 if shape in {"inventory", "timeline", "synthesis", "conflict", "audit"} else 1,
            "contradiction_resolution_required": shape == "conflict" or any(marker in str(query) for marker in _CONFLICT_MARKERS),
        },
        "relationship_types": list(dict.fromkeys(
            ["entity_relation"] if graph_required else []
        )),
        "graph_required": graph_required,
        "graph_budget": graph_budget,
    }


def _entity_pairs(values: Any) -> tuple[list[str], list[str]]:
    ids: list[str] = []
    names: list[str] = []
    for value in values or []:
        if isinstance(value, dict):
            entity_id = str(value.get("id") or "").strip()
            name = str(value.get("name") or value.get("label") or "").strip()
        else:
            entity_id = ""
            name = str(value or "").strip()
        if entity_id and entity_id not in ids:
            ids.append(entity_id)
        if name and name not in names:
            names.append(name)
    return ids, names


def project_record_index(item: dict[str, Any]) -> dict[str, Any]:
    """Project additive query metadata without changing the Bank record."""
    metadata = dict(item.get("metadata") or {})
    subject_ids, subject_names = _entity_pairs(item.get("entities"))
    subject_ids.extend(str(value) for value in metadata.get("subject_ids") or [] if str(value) not in subject_ids)
    subject_names.extend(str(value) for value in metadata.get("subject_names") or [] if str(value) not in subject_names)
    source_ids = [str(value) for value in (
        item.get("document_id"), metadata.get("source_document_id"), metadata.get("source_uri")
    ) if value not in (None, "")]
    relation_values = metadata.get("relationship_types") or metadata.get("relation_types") or []
    if isinstance(relation_values, str):
        relation_values = [relation_values]
    if metadata.get("relation_type"):
        relation_values = [*relation_values, metadata["relation_type"]]
    return {
        "record_id": str(item.get("id") or item.get("chunk_id") or ""),
        "memory_type": str(item.get("type") or item.get("memory_type") or "unknown"),
        "subject_ids": list(dict.fromkeys(subject_ids)),
        "subject_names": list(dict.fromkeys(subject_names)),
        "observed_at": item.get("mentioned_at") or item.get("occurred_start") or metadata.get("observed_at"),
        "validity": {
            "valid_from": metadata.get("valid_from") or item.get("occurred_start"),
            "valid_to": metadata.get("valid_to") or item.get("occurred_end"),
            "status": metadata.get("validity") or metadata.get("status") or item.get("state") or "unknown",
            "supersedes": list(metadata.get("supersedes") or []),
            "superseded_by": list(metadata.get("superseded_by") or []),
        },
        "task": {
            "project_key": metadata.get("project_key") or metadata.get("project"),
            "task_id": metadata.get("task_id"),
            "topic": metadata.get("topic"),
        },
        "source_ids": list(dict.fromkeys(source_ids)),
        "source_classes": [str(metadata["source"])] if metadata.get("source") else [],
        "relationship_types": list(dict.fromkeys(str(value) for value in relation_values if str(value))),
        "contradiction_ids": list(metadata.get("contradiction_ids") or []),
        "conflict_state": metadata.get("conflict_state") or "unknown",
    }


def _score(item: dict[str, Any]) -> float | None:
    scores = item.get("scores") or {}
    for value in (scores.get("final"), item.get("score"), (item.get("metadata") or {}).get("semantic_relevance_score")):
        if isinstance(value, (int, float)):
            return float(value)
    return None


def evaluate_evidence_quality(query: str, results: list[dict[str, Any]], contract: dict[str, Any]) -> dict[str, Any]:
    """Assess whether missing evidence can justify a broader research route."""
    projections = [project_record_index(item) for item in results]
    reasons: list[str] = []
    numeric_scores = [value for item in results if (value := _score(item)) is not None]
    if not results:
        reasons.append("no_results")
    elif numeric_scores and max(numeric_scores) < 0.45:
        reasons.append("low_relevance")

    required_subjects = list(contract.get("subjects") or [])
    if required_subjects:
        corpus = "\n".join(
            [str(item.get("text") or item.get("content") or "") for item in results]
            + [" ".join(row["subject_ids"] + row["subject_names"]) for row in projections]
        ).casefold()
        covered_subjects = [
            subject["id"] for subject in required_subjects
            if any(str(value).casefold() in corpus for value in [subject.get("id"), subject.get("name"), *(subject.get("aliases") or [])] if str(value))
        ]
        if len(covered_subjects) < len(required_subjects):
            reasons.append("incomplete_subject_coverage")
    else:
        covered_subjects = []

    distinct_sources = {
        value for row in projections for value in [*row["source_ids"], *row.get("source_classes", [])] if value
    }
    minimum_sources = int((contract.get("evidence") or {}).get("minimum_sources") or 1)
    if (contract.get("evidence") or {}).get("required") and len(distinct_sources) < minimum_sources:
        reasons.append("insufficient_source_coverage")

    temporal = dict(contract.get("temporal") or {})
    observed = sorted({str(row["observed_at"]) for row in projections if row.get("observed_at")})
    if temporal.get("start") and temporal.get("end") and len(observed) < 2:
        reasons.append("insufficient_temporal_coverage")

    unresolved = [
        row["record_id"] for row in projections
        if row["contradiction_ids"] and row["conflict_state"] not in {"resolved", "superseded", "retracted"}
    ]
    if unresolved or (
        (contract.get("evidence") or {}).get("contradiction_resolution_required")
        and results
        and not any(row["conflict_state"] in {"resolved", "superseded", "retracted"} for row in projections)
    ):
        reasons.append("unresolved_contradictions")

    broad = contract.get("shape") in {"inventory", "timeline", "synthesis", "conflict", "audit"} or any(
        marker in str(query) for marker in _BROAD_MARKERS
    )
    needs_escalation = bool(reasons)
    recommended = "research" if needs_escalation and broad else ("recall_expand" if needs_escalation else "none")
    return {
        "schema": "evolving-profile.evidence-quality.v1",
        "result_count": len(results),
        "relevance": {"scored": len(numeric_scores), "best": max(numeric_scores) if numeric_scores else None},
        "source_coverage": {"distinct": len(distinct_sources), "required": minimum_sources},
        "subject_coverage": {"covered": covered_subjects, "required": [row["id"] for row in required_subjects]},
        "temporal_coverage": {"observed_points": len(observed), "window": temporal},
        "unresolved_contradiction_ids": unresolved,
        "needs_escalation": needs_escalation,
        "recommended_route": recommended,
        "reasons": list(dict.fromkeys(reasons)),
    }
