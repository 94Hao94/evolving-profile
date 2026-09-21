"""Progressive memory access router for the user-centred Hindsight V3 layout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DIRECT_EVIDENCE_TERMS = (
    "原话", "来源", "哪次", "什么时候说", "时间找出来", "证据",
    "豆包里", "千问里", "飞书里",
)

DOMAIN_KEYWORDS = {
    "learning": ("学习", "复习", "课程", "知识", "训练", "考试", "数学"),
    "work": ("工作", "客户", "项目", "方案", "采购", "高校", "投标", "产品"),
    "personal": ("生活", "家庭", "孩子", "个人", "偏好", "习惯"),
    "ai": ("ai", "模型", "codex", "openclaw", "智能体", "记忆系统"),
}


def load_policy(path: Path | str) -> dict[str, Any]:
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    if policy.get("schema") != 3:
        raise ValueError("memory access policy schema must be 3")
    if not policy.get("sharedBank") or "roles" not in policy:
        raise ValueError("memory access policy lacks sharedBank or roles")
    return policy


def _domains(query: str) -> set[str]:
    normalized = "".join(query.split()).casefold()
    return {
        domain
        for domain, keywords in DOMAIN_KEYWORDS.items()
        if any(keyword.casefold() in normalized for keyword in keywords)
    }


def build_plan(role: str, query: str, policy: dict[str, Any]) -> dict[str, Any]:
    role_policy = policy["roles"].get(role, policy["roles"]["default"])
    allowed = list(role_policy["allowedLevels"])
    levels = list(role_policy["initialLevels"])
    domains = _domains(query)
    direct_evidence = any(term in query.casefold() for term in DIRECT_EVIDENCE_TERMS)
    cross_domain = len(domains) >= 2 or any(
        marker in query for marker in ("结合我最近", "跨领域", "综合我", "联系我的")
    )

    if cross_domain:
        for level in ("facts", "events"):
            if level in allowed and level not in levels:
                levels.append(level)
    if direct_evidence:
        for level in ("facts", "events", "raw"):
            if level in allowed and level not in levels:
                levels.append(level)

    banks = [policy["sharedBank"]]
    if role_policy.get("roleBank"):
        banks.append(role_policy["roleBank"])
    if "raw" in levels and policy.get("evidenceBank"):
        banks.append(policy["evidenceBank"])

    return {
        "role": role,
        "access_class": role_policy["accessClass"],
        "shared_bank": policy["sharedBank"],
        "role_bank": role_policy.get("roleBank"),
        "evidence_bank": policy.get("evidenceBank"),
        "levels": levels,
        "allowed_levels": allowed,
        "banks": list(dict.fromkeys(banks)),
        "domains": sorted(domains),
        "direct_evidence": direct_evidence,
        "cross_domain": cross_domain,
        "initial_token_budget": int(role_policy["initialTokenBudget"]),
        "expanded_token_budget": int(role_policy["expandedTokenBudget"]),
        "auto_expand": bool(role_policy["autoExpand"]),
    }
