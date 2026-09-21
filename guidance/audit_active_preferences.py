"""Audit active preference revisions before they influence new tasks.

The audit annotates the registry; it never withdraws or rewrites content. Rules
are conservative and explain why an item is restricted or needs review.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import datetime as dt
import json
from pathlib import Path
import re
import sys

from mcp_runtime import load_repository

PATH_OR_IDENTIFIER = re.compile(r"(?:/Users/|/tmp/|\.docx|\.pptx|\.xlsx|\.xls|\.pdf|[A-Za-z0-9_]+@[A-Za-z0-9_-]+|oc_[a-z0-9]+)", re.I)
PROJECT_MARKERS = re.compile(r"(?:这个项目|本项目|这个文件|这张图|这次|本次|农学院|天津职业大学|河北工业大学|天津理工大学|WPS Cloud Files)")
METHOD_MARKERS = re.compile(r"(?:必须使用|只能使用|固定使用|升级到|版本|端口|模型|工具|接口|流程|方法|保证|永远|每10分钟|每30分钟|不能用)")
TEMPORAL_MARKERS = re.compile(r"(?:当前|现在|最近|今天|昨天|本轮|临时|截至|旧版|新版本|升级后)")
# These phrases describe how to reconcile a preference with the current user
# request; they are exception/boundary language, not claims that the
# preference itself will expire. Remove only the narrow exception clauses
# before checking temporal validity.
TEMPORAL_EXCEPTION_PHRASES = (
    "当前要求简短、不要音标或采用其他格式时，按当前要求",
    "当前要求",
)
EXECUTION_ABSOLUTES = re.compile(r"(?:必须|严禁|只能|保证|永远|自动执行|直接执行|无需判断|完全按照|一律)")
PRODUCT_STATE_MARKERS = re.compile(r"(?:当前|现在|已完成|已生效|正式|版本|架构|界面|功能|保留核心功能|四层|星座图|图谱)")


def audit_unit(unit: dict) -> dict:
    prior=(unit.get('preference_audit') or {}).get('audit') or {}
    if prior.get('review_kind')=='source_checked_manual':
        # Audit metadata is attached to the exact active revision. A generic
        # keyword pass must not undo a documented source review of that body.
        return {**prior,'flags':prior.get('flags',[])}
    text = str(unit.get("text") or "")
    temporal_scan_text = text
    for phrase in TEMPORAL_EXCEPTION_PHRASES:
        temporal_scan_text = temporal_scan_text.replace(phrase, "")
    refs = unit.get("evidence_refs") or []
    families = {ref.get("document_id") for ref in refs if ref.get("document_id")}
    flags, reasons = [], []
    if PATH_OR_IDENTIFIER.search(text):
        flags.append("identifier_or_path"); reasons.append("正文含项目路径、群ID、文件扩展名或精确标识，默认限制在原范围")
    if PROJECT_MARKERS.search(text):
        flags.append("project_specific"); reasons.append("正文含项目/客户限定词，不能作为全局偏好")
    if METHOD_MARKERS.search(text):
        flags.append("method_claim"); reasons.append("正文含工具、版本、流程或效果主张，需要当前资料或真实测试复核")
    if TEMPORAL_MARKERS.search(temporal_scan_text):
        flags.append("temporal_claim"); reasons.append("正文含时效性词，后续纠正或版本变化可能使其失效")
    if EXECUTION_ABSOLUTES.search(text):
        flags.append("execution_absolute"); reasons.append("正文使用绝对执行措辞，必须降级为参考，不能覆盖当前Agent判断")
    if PRODUCT_STATE_MARKERS.search(text) and ("Hindsight" in text or "hindsight" in text):
        flags.append("product_state_sensitive"); reasons.append("正文依赖产品架构或界面状态，当前实现变化后应标记替代而非继续注入")
    if len(families) <= 1:
        flags.append("single_source_family")
    nature = unit.get("nature")
    if "method_claim" in flags or "temporal_claim" in flags or "product_state_sensitive" in flags:
        state = "needs_review"
    elif "identifier_or_path" in flags or "project_specific" in flags:
        state = "restricted"
    elif nature == "inferred_pattern" and len(families) < 2:
        state = "needs_review"
        reasons.append("inferred_pattern缺少两个独立来源家族")
    else:
        state = "approved"
    if not reasons:
        reasons.append("用户来源可回读，范围和当前语义未触发限制规则")
    return {"state": state, "scope_level": "project" if "project_specific" in flags else "domain" if flags else "global",
            "validity_kind": "volatile_method" if {"method_claim","execution_absolute","product_state_sensitive"} & set(flags) else "context_sensitive" if flags else "stable",
            "flags": flags, "reason": "；".join(reasons), "source_family_count": len(families),
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat()}


def audit_repository(repo, apply: bool = False) -> dict:
    units = repo.active_units(); rows = []
    for unit in units:
        result = audit_unit(unit)
        row = {"id": unit["id"], "revision": unit["revision"], "text": unit.get("text"), **result}
        rows.append(row)
        if apply:
            repo.set_unit_audit(unit["id"], unit["revision"], result)
    return {"schema": "guidance.active-preference-audit.v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "active_units": len(units), "state_counts": dict(Counter(row["state"] for row in rows)),
            "flag_counts": dict(Counter(flag for row in rows for flag in row["flags"])), "items": rows,
            "applied": apply, "boundary": "Audit metadata changes selection eligibility only; no preference body or source is rewritten and no unit is withdrawn."}


def apply_known_supersessions(repo) -> list[dict]:
    """Apply only explicit current-state supersessions, preserving history."""
    results = []
    for unit in repo.active_units():
        text = str(unit.get("text") or "")
        if "在基于Hindsight的产品迭代中" in text and "严禁删减或替换为轻量原型" in text:
            results.append(repo.mark_unit_superseded(
                unit["id"], unit["revision"],
                superseded_by="current-hindsight-guidance-state-20260911",
                reason="当前用户已明确Hindsight产品形态和功能边界已发生变化；旧条目中的固定四层、原版界面和‘严禁替换’是历史阶段性约束，不再作为当前执行规则。保留原文与来源，仅从前台选择中排除。"))
    return results


def main(config_path: str, output_path: str, apply: bool = False):
    repo = load_repository(config_path)
    result = audit_repository(repo, apply=apply)
    superseded = apply_known_supersessions(repo) if apply else []
    result["known_supersessions"] = superseded
    Path(output_path).parent.mkdir(parents=True, exist_ok=True); Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({key: result[key] for key in ("active_units", "state_counts", "flag_counts", "applied")}, ensure_ascii=False))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument("config"); parser.add_argument("output"); parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(); main(args.config, args.output, args.apply)
