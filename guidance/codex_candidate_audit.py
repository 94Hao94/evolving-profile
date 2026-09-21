"""Deterministic Codex-side candidate inventory; no external model call or publish."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re
import sqlite3
import sys

from raw_preference_pipeline import clean_user_text, load_raw_messages, reviewable_message

CATEGORIES = {
    "communication": ("表达", "简洁", "文字", "语气", "领导", "客户", "说法", "叫", "名称"),
    "learning": ("理解", "解释", "例子", "打比方", "复习", "学习", "机制", "全称", "音标", "逻辑"),
    "reasoning": ("分析", "判断", "原因", "证据", "权衡", "建议", "推荐", "泛化", "过拟合", "过时", "方法"),
    "collaboration": ("继续", "执行", "推进", "不要停", "授权", "工具", "skill", "协作", "后台", "模型"),
    "delivery": ("交付", "验收", "测试", "审计", "视觉", "图", "格式", "文档", "PPT", "回归", "复测", "截图"),
}
HIGH_RISK = re.compile(r"(?:人名|姓名|品牌|型号|IP|端口|金额|预算|日期|时间|数量|不要|不能|禁止|必须)")


def classify(text: str) -> list[str]:
    return [key for key, words in CATEGORIES.items() if any(word.casefold() in text.casefold() for word in words)]


def candidate_from_message(row: dict) -> dict | None:
    text = row["text"]
    cats = classify(text)
    if not cats:
        return None
    scope = "task" if re.search(r"(?:本次|这次|刚才|今天|这个文件|这个项目|这张图|当前)", text) else "domain"
    if re.search(r"(?:所有|以后|每次|长期|一直|都要|不要总)", text):
        scope = "global" if not re.search(r"(?:本项目|这个项目|这个文件|本次|这张图)", text) else "domain"
    disposition = "task_local" if scope == "task" else "candidate"
    nature = "explicit_requirement" if re.search(r"(?:必须|一定要|以后|不要|不能|禁止|要求|只要|除非|改成|换成|保留|隐藏|删除)", text) else "declared_preference"
    return {"source_item_id": row["thread_id"] + ":" + row["item_id"], "event_at": row["created_at"], "verbatim_quote": text,
            "candidate_text": text, "primary_category": cats[0], "related_categories": cats[1:], "nature": nature,
            "disposition": disposition, "scope_level": scope, "scope": {"domains": [], "media": [], "projects": []},
            "validity_kind": "volatile_method" if HIGH_RISK.search(text) and any(x in text for x in ("方法", "工具", "版本", "端口", "模型")) else "context_sensitive",
            "method_claims": [text] if any(x in text for x in ("方法", "工具", "版本", "模型", "流程")) else [],
            "conflict_signals": [], "asr_corrections": [], "uncertain_terms": [],
            "reason": "deterministic_signal_inventory; requires Codex semantic audit"}


def main(input_path: str, output_path: str):
    report = json.loads(Path(input_path).read_text())
    rows = [row for row in report["items"] if row.get("reviewable")]
    candidates = [candidate for row in rows if (candidate := candidate_from_message(row))]
    families = {}
    for candidate in candidates:
        key = re.sub(r"\s+", "", candidate["candidate_text"]).strip("。！？，, ").casefold()
        families.setdefault(key, []).append(candidate)
    compact = []
    for key, members in families.items():
        first = members[0]; documents = sorted({item["source_item_id"].split(":", 1)[0] for item in members})
        compact.append({"family_key": key, "text": first["candidate_text"], "primary_category": first["primary_category"],
                        "nature": first["nature"], "scope_level": first["scope_level"], "occurrences": len(members),
                        "independent_threads": len({item["source_item_id"].split(":", 1)[0] for item in members}),
                        "event_at_min": min(item["event_at"] for item in members), "event_at_max": max(item["event_at"] for item in members),
                        "items": members})
    result = {"schema": "guidance.codex-candidate-audit.v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "source_inventory": str(input_path), "reviewable_messages": len(rows), "raw_candidates": len(candidates),
              "candidate_families": len(compact), "families": sorted(compact, key=lambda row: (-row["independent_threads"], row["family_key"])),
              "boundary": "Codex deterministic inventory only; semantic scope, ASR, method, staleness and publication review remain required."}
    target = Path(output_path); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({key: result[key] for key in ("reviewable_messages", "raw_candidates", "candidate_families")}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
