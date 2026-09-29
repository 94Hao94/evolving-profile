"""Conservative stable-profile projection over reviewed guidance units."""
from __future__ import annotations

import re


_NARROW_TERMS = re.compile(
    r"ppt|pptx|word|docx|客户拜访|签到|报销|招投标|标书|高校|课程|"
    r"小黛|trainer|flclash|computer\s*use|记忆系统|链路页|crm|视频|字幕|"
    r"网页|网站|按钮|公文|演示|文档|图表|示意图|项目名称|产品型号",
    re.I,
)

_CROSS_SCENARIO = re.compile(
    r"当前用户|当前要求|权威来源|证据|目标|约束|未完成|完成前|"
    r"事实.*假设|冲突|来源|授权|不要停|持续核对|多步骤|阶段性结果",
    re.I,
)


def _reviewed_stable(unit: dict) -> bool:
    audit = unit.get("preference_audit") or {}
    return (
        audit.get("state") == "approved"
        and audit.get("validity_kind") == "stable"
        and audit.get("scope_level") == "global"
    )


def _corpus(unit: dict) -> str:
    return " ".join([
        str(unit.get("text") or ""),
        *[str(value) for value in unit.get("applies_when") or []],
        *[str(value) for value in unit.get("exceptions") or []],
    ])


def preference_candidate(unit: dict) -> dict:
    manifest=[{key:ref.get(key) for key in ('memory_id','document_id','chunk_id','stored_role','origin','source_revision')}
              for ref in (unit.get('evidence_refs') or [])[:3]]
    return {
        key: unit.get(key) for key in (
            "id", "revision", "primary_category", "nature", "text", "scope",
            "applies_when", "exceptions", "effect_on_action",
        )
    } | {
        "status": "candidate_requires_agent_judgment",
        "may_override_current_prompt": False,
        "source_locator": {
            "tool": "read_preference_unit",
            "id": unit.get("id"),
            "revision": unit.get("revision"),
        },
        "evidence_manifest": manifest,
    }


def stable_profile(units: list[dict], limit: int = 12) -> list[dict]:
    rows = []
    for unit in units:
        text = _corpus(unit)
        if not _reviewed_stable(unit) or _NARROW_TERMS.search(text) or not _CROSS_SCENARIO.search(text):
            continue
        row = preference_candidate(unit)
        row["status"] = "stable_profile_advisory"
        rows.append(row)
    return rows[:limit]
