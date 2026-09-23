"""Codex-only review gates for ASR cleanup, scope, staleness and method risk."""
from __future__ import annotations

from collections import Counter
import datetime as dt
from hashlib import sha256
import json
from pathlib import Path
import re


METHOD = re.compile(r"(?:必须用|只能用|固定用|换成|升级到|版本|端口|模型|工具|接口|流程|方法|一定能|保证|永远)")
PROJECT = re.compile(r"(?:这个项目|本项目|这次|本次|这个文件|这张图|昨天|今天|刚才|给[\u4e00-\u9fff]{1,12}写|发到.+群)")
GLOBAL = re.compile(r"(?:以后|每次|所有|长期|一直|通常|默认|不要总|都要|均应)")
HIGH_RISK = re.compile(r"(?:人名|姓名|品牌|型号|IP|端口|金额|预算|日期|时间|数量|身份证|车牌|账号|群ID)")
ASR_COMMON = {
    "纬度": "维度", "心智模形": "心智模型", "心知模型": "心智模型", "行为模形": "行为模型",
    "星座圖": "星座图", "图普": "图谱", "过拟和": "过拟合", "hindsight": "Hindsight",
    "codex": "Codex", "claude code": "Claude Code", "openclaw": "OpenClaw",
}


def conservative_canonical(text: str) -> tuple[str, list[dict], list[str]]:
    value = str(text or "")
    corrections, uncertain = [], []
    for source, target in ASR_COMMON.items():
        if source in value and source != target:
            value = value.replace(source, target)
            corrections.append({"from": source, "to": target, "basis": "stable domain vocabulary or immediate sentence context", "confidence": 0.98})
    if HIGH_RISK.search(value):
        # Do not silently normalize high-risk tokens from speech-like text.
        for token in re.findall(r"[A-Za-z]{2,}[\w.-]*|\d+[A-Za-z\w.-]*", value):
            if token.lower() not in {"PPT", "PDF", "MD", "AI", "MCP", "RAG", "WPS", "IP"}:
                uncertain.append(token)
    return value, corrections, sorted(set(uncertain))


def scope_for(text: str, family_size: int, thread_count: int) -> str:
    if PROJECT.search(text):
        return "project" if family_size > 1 else "task"
    if GLOBAL.search(text) and thread_count >= 2:
        return "global"
    return "domain"


def preference_kind_for(text: str) -> str:
    if "解释" in text and ("先" in text or "例子" in text):
        return "explanation_structure"
    if any(value in text for value in ("验证", "测试", "验收", "审计", "检查")):
        return "verification"
    if any(value in text for value in ("界面", "视觉", "布局", "图", "颜色")):
        return "visual_presentation"
    if METHOD.search(text):
        return "delivery_method"
    return "interaction_behavior"


def polarity_for(text: str) -> str:
    if any(value in text for value in ("严禁", "禁止", "不能", "不要")):
        return "forbid"
    if any(value in text for value in ("必须", "务必", "一定要")):
        return "require"
    if any(value in text for value in ("不喜欢", "避免")):
        return "avoid"
    return "prefer"


def review_family(family: dict) -> dict:
    text = family["text"]
    canonical, corrections, uncertain = conservative_canonical(text)
    family_size, threads = int(family.get("occurrences", 0)), int(family.get("independent_threads", 0))
    scope = scope_for(text, family_size, threads)
    method_risk = bool(METHOD.search(text))
    reasons = []
    disposition = "hold"
    if uncertain:
        reasons.append("uncertain_high_risk_asr_terms")
    if scope in {"task", "project"}:
        reasons.append("local_scope")
    if method_risk:
        reasons.append("method_requires_current_validation")
    if not reasons and scope == "global":
        disposition = "reviewable_global_preference"
    elif not reasons and threads >= 2:
        disposition = "reviewable_inferred_pattern"
    family_id = "family:" + sha256(str(family["family_key"]).encode()).hexdigest()[:20]
    publication_state = "reviewed_preference" if disposition.startswith("reviewable") else "observation_candidate"
    return {"family_key": family["family_key"], "verbatim_quote": text, "canonical_text": canonical,
            "asr_corrections": corrections, "uncertain_terms": uncertain, "scope_level": scope,
            "independent_threads": threads, "occurrences": family_size, "method_risk": method_risk,
            "disposition": disposition, "review_reasons": reasons,
            "preference_kind": preference_kind_for(canonical), "polarity": polarity_for(canonical),
            "validity_kind": "volatile_method" if method_risk else ("context_sensitive" if scope in {"task", "project"} else "stable"),
            "confidence_inputs": {"explicitness": 1.0 if GLOBAL.search(canonical) else 0.6,
                                  "independence": min(1.0, threads / 3), "support": min(1.0, family_size / 3)},
            "support_count": family_size, "contradiction_count": int(family.get("contradiction_count") or 0),
            "source_turn_ids": sorted({str(item.get("turn_id")) for item in family.get("items") or [] if item.get("turn_id")}),
            "source_family_ids": [family_id], "supersedes": list(family.get("supersedes") or []),
            "superseded_by": list(family.get("superseded_by") or []),
            "cross_cutting": bool(scope == "global" and preference_kind_for(canonical) in {"explanation_structure", "verification", "interaction_behavior"}),
            "publication_state": publication_state,
            "audit": {"source_event_at_min": family.get("event_at_min"), "source_event_at_max": family.get("event_at_max"),
                      "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}}


def audit_file(input_path: str | Path, output_path: str | Path) -> dict:
    source = json.loads(Path(input_path).read_text())
    reviews = [review_family(family) for family in source.get("families", [])]
    report = {"schema": "guidance.codex-preference-review.v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "source": str(input_path), "families": len(reviews), "reviewable": sum(r["disposition"].startswith("reviewable") for r in reviews),
              "held": sum(r["disposition"] == "hold" for r in reviews), "reasons": Counter(reason for row in reviews for reason in row["review_reasons"]),
              "items": reviews, "boundary": "Codex review gates do not publish or change active registry; method claims still need external/current verification."}
    report["reasons"] = dict(report["reasons"])
    Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report
