"""Source-linked Session state and deterministic three-tier navigation summaries."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from .context_summary import BUDGETS, bounded_summary


FORM_TAG = "send_user_message_question_reply"
FORM_PATTERN = re.compile(rf"^\s*<{FORM_TAG}>\s*(.*?)\s*</{FORM_TAG}>\s*$", re.S)
STATE_FIELDS = ("subject", "goal", "phase", "constraints", "corrections", "assistant_reports", "unresolved")
PHASE_LABELS = {"requested": "待处理", "in_progress": "讨论或执行中",
                "assistant_reported": "助手有后续答复（执行结果未独立核验）", "unknown": "状态未核实"}
CORRECTION_HINT = re.compile(r"不要|别再|别写|不是|改成|改为|更正|纠正|名字叫|正确写法|实际上")


def parse_form_reply(text: str) -> list[dict] | None:
    match = FORM_PATTERN.fullmatch(str(text or ""))
    if not match:
        return None
    try:
        rows = json.loads(match.group(1))
    except (TypeError, ValueError):
        return None
    if not isinstance(rows, list) or not rows:
        return None
    result = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        question, answer = row.get("question"), row.get("answer")
        if not isinstance(question, str) or not question.strip() or not isinstance(answer, str) or not answer.strip():
            return None
        result.append({"question": question.strip(), "answer": answer.strip()})
    return result


def project_source_messages(source: dict) -> list[dict]:
    from source_safety import mask_text

    projected = []
    for row in source.get("messages") or []:
        raw = str(row.get("text") or "")
        if raw.lstrip().startswith(f"<{FORM_TAG}>"):
            answers = parse_form_reply(raw)
            if answers:
                body = "；".join(f"问题：{item['question']} 回答：{item['answer']}" for item in answers)
                kind = "structured_user_answer"
            else:
                body, kind = "[结构化表单答复无法解析，需回读原文]", "opaque_structured_reply"
        else:
            body = raw
            kind = "user_direct" if row.get("role") == "user" else "assistant_report_only"
        if row.get("merge_projection"):
            kind = "source_linked_state_candidate"
        projected.append({"message_id": row.get("evidence_id"), "role": row.get("role"),
                          "at": row.get("at"), "turn_id": row.get("turn_id"),
                          "text": mask_text(body), "provenance_kind": kind})
    return projected


def correction_review_hints(source: dict, limit: int = 12) -> list[dict]:
    """Focus model attention without treating keyword matches as corrections."""
    from source_safety import mask_text

    hints = []
    for row in source.get("messages") or []:
        text = str(row.get("text") or "")
        if row.get("role") != "user" or text.lstrip().startswith(f"<{FORM_TAG}>"):
            continue
        matches = list(CORRECTION_HINT.finditer(text))
        if not matches:
            continue
        last = matches[-1]
        excerpt = " ".join(text[max(0, last.start() - 80):last.end() + 120].split())
        hints.append({"message_id": row.get("evidence_id"), "excerpt": mask_text(excerpt),
                      "evidence_role": "review_hint_not_verified_claim"})
    return hints[-max(1, min(200, int(limit))):]


def _claim(value: object, source_by_id: dict, allowed_role: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"text", "message_ids"}:
        raise ValueError("scenario_state_invalid")
    text = value.get("text")
    ids = value.get("message_ids")
    if not isinstance(text, str) or not text.strip() or len(text) > 180 or not isinstance(ids, list) or not 1 <= len(ids) <= 4:
        raise ValueError("scenario_state_invalid")
    if len(set(ids)) != len(ids) or any(not isinstance(mid, str) or mid not in source_by_id for mid in ids):
        raise ValueError("scenario_evidence_id_invalid")
    if any(source_by_id[mid]["role"] != allowed_role for mid in ids):
        raise ValueError("scenario_state_role_invalid")
    return {"text": " ".join(text.split()), "message_ids": ids}


def _list_claims(value: object, source_by_id: dict, role: str) -> list[dict]:
    if not isinstance(value, list) or len(value) > 8:
        raise ValueError("scenario_state_invalid")
    return [_claim(item, source_by_id, role) for item in value]


def _render_tiers(state: dict) -> dict:
    compact_lines = [f"对象：{state['subject']['text']}", f"任务：{state['goal']['text']}",
                     f"当前阶段：{PHASE_LABELS[state['phase']]}"]
    if state["phase"] == "assistant_reported" and state["assistant_reports"]:
        compact_lines.append("最近进展：助手有后续答复（详情见标准层；未独立核验）")
    if state["unresolved"]:
        compact_lines.append("待核：" + state["unresolved"][0]["text"])
    compact = "\n".join(compact_lines)
    standard_lines = list(compact_lines)
    for title, field in (("关键约束", "constraints"), ("后续纠正", "corrections")):
        standard_lines.extend(f"{title}：{item['text']}" for item in state[field][:3])
    if state["assistant_reports"]:
        standard_lines.append("助手报告（未独立核验）：" + state["assistant_reports"][-1]["text"])
    if len(state["unresolved"]) > 1:
        standard_lines.extend("其他待核：" + item["text"] for item in state["unresolved"][1:3])
    standard = "\n".join(standard_lines)
    full_lines = [f"对象：{state['subject']['text']} [来源:{','.join(state['subject']['message_ids'])}]",
                  f"任务：{state['goal']['text']} [来源:{','.join(state['goal']['message_ids'])}]",
                  f"当前阶段：{PHASE_LABELS[state['phase']]}"]
    for title, field in (("约束", "constraints"), ("纠正", "corrections"),
                         ("助手报告（未独立核验）", "assistant_reports"), ("未决", "unresolved")):
        for item in state[field]:
            full_lines.append(f"{title}：{item['text']} [来源:{','.join(item['message_ids'])}]")
    return {"compact": compact, "standard": standard, "full": "\n".join(full_lines)}


def validate_state_draft(source: dict, state: dict, *, model: str) -> dict:
    if source.get("status") != "complete" or not source.get("messages") or not source.get("source_revision"):
        raise ValueError("scenario_source_incomplete")
    if not isinstance(state, dict) or set(state) != set(STATE_FIELDS):
        raise ValueError("scenario_state_invalid")
    source_by_id = {row["evidence_id"]: row for row in source["messages"]}
    normalized = {"subject": _claim(state["subject"], source_by_id, "user"),
                  "goal": _claim(state["goal"], source_by_id, "user")}
    phase = state.get("phase")
    if phase not in PHASE_LABELS:
        raise ValueError("scenario_state_phase_invalid")
    normalized["phase"] = phase
    for field, role in (("constraints", "user"), ("corrections", "user"),
                        ("assistant_reports", "assistant"), ("unresolved", "user")):
        normalized[field] = _list_claims(state[field], source_by_id, role)
    last = source["messages"][-1]
    if last["role"] == "user":
        if phase not in {"requested", "unknown"}:
            raise ValueError("scenario_state_phase_invalid")
    if last["role"] == "user" and parse_form_reply(last["text"]) is None:
        if not any(last["evidence_id"] in item["message_ids"] for item in normalized["unresolved"]):
            raise ValueError("scenario_state_unresolved_final_request")
    if phase == "assistant_reported" and (not normalized["assistant_reports"] or
            not any(last["evidence_id"] in item["message_ids"] for item in normalized["assistant_reports"])):
        raise ValueError("scenario_state_phase_invalid")
    tiers = _render_tiers(normalized)
    summaries = {}
    for tier, text in tiers.items():
        bounded, receipt = bounded_summary(text, "session", tier)
        if not bounded or receipt["truncated"] or len(text) > BUDGETS["session"][tier]["max_chars"]:
            raise ValueError("scenario_summary_budget_or_empty")
        summaries[tier] = bounded
    evidence = [{"statement": item["text"], "message_ids": item["message_ids"], "field": field}
                for field in ("subject", "goal") for item in [normalized[field]]]
    evidence.extend({"statement": item["text"], "message_ids": item["message_ids"], "field": field}
                    for field in ("constraints", "corrections", "assistant_reports", "unresolved")
                    for item in normalized[field])
    unknowns = [item["text"] for item in normalized["unresolved"]]
    if last["role"] == "user" and parse_form_reply(last["text"]) is None:
        unknowns.append("最后一条用户请求后未见助手最终答复。")
    return {"schema": "evolving-profile.scenario-draft.v3", "context_id": "session:" + source["thread_id"],
            "context_type": "session", "status": "source_linked_draft", "review_status": "pending_independent_review",
            "source_check": "message_id_and_role_only_not_semantic_entailment",
            "source": source.get("source"), "source_files": source.get("source_files") or [],
            "source_revision": source["source_revision"], "source_message_count": len(source["messages"]),
            "summary_model": model, "generated_at": datetime.now(timezone.utc).isoformat(),
            "state": normalized, "summaries": summaries, "evidence": evidence, "unknowns": unknowns,
            "evidence_role": "context_navigation_only"}
