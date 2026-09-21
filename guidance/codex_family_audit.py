"""Family-level Codex audit for raw preference candidates.

This is intentionally conservative: it produces a review queue, not active
memory. Publication still needs Hindsight source witnesses and a final review.
"""
from __future__ import annotations

from collections import defaultdict, Counter
import datetime as dt
import json
from pathlib import Path
import re


QUESTION = re.compile(r"^(?:请|能不能|你看看|你再|你现在|这个|如何|为什么|什么|是不是|对吧|明白|那你|帮我|给我|解释|说明|回顾|审查|检查|总结|告诉我|先说|有没有|怎么|是否|具体)")
PATH = re.compile(r"(?:/Users/|/tmp/|\.docx|\.pptx|\.xlsx|\.xls|\.pdf|Codex-clipboard|filecache)", re.I)
LOCAL = re.compile(r"(?:这个项目|本项目|这次|本次|这个文件|这张图|昨天|今天|刚才|给[\u4e00-\u9fff]{1,12}写|发到.+群|当前版本)")
METHOD = re.compile(r"(?:必须用|只能用|固定用|升级到|版本|端口|模型|工具|接口|流程|方法|一定能|保证|永远|每10分钟|每30分钟)")
PREFERENCE = re.compile(r"(?:偏好|喜欢|更喜欢|不喜欢|以后|每次|所有|长期|通常|默认|都要|不要|不能|禁止|必须|优先|保留|拒绝|倾向|希望|重视|强调)")


def family_key(text: str) -> str:
    value = re.sub(r"\s+", "", str(text or ""))
    value = re.sub(r"[。！？!?，,；;：:、]", "", value)
    return value.casefold()


def audit(items: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        groups[family_key(item.get("canonical_text") or item.get("verbatim_quote"))].append(item)
    families = []
    for key, members in groups.items():
        text = members[0].get("canonical_text") or members[0].get("verbatim_quote") or ""
        threads = sorted({item.get("source_item_id", "").split(":", 1)[0] for item in members})
        flags = []
        if QUESTION.search(text): flags.append("question_or_explanation_request")
        if PATH.search(text): flags.append("path_or_file_specific")
        if LOCAL.search(text): flags.append("local_scope_signal")
        if METHOD.search(text): flags.append("method_or_volatile_claim")
        if not PREFERENCE.search(text): flags.append("no_preference_marker")
        if len(threads) < 2: flags.append("single_thread")
        if any(item.get("review_flags") for item in members): flags.append("high_risk_token")
        if not flags and len(threads) >= 2:
            disposition = "codex_reviewable_general_pattern"
        elif ("question_or_explanation_request" in flags and len(threads) >= 2 and
              not ({"method_or_volatile_claim", "path_or_file_specific", "local_scope_signal", "high_risk_token"} & set(flags))):
            disposition = "codex_reviewable_after_question_rewrite"
        else:
            disposition = "held"
        families.append({"family_key": key, "canonical_text": text, "verbatim_quotes": sorted({item.get("verbatim_quote", "") for item in members}),
                         "primary_categories": sorted({item.get("primary_category") for item in members if item.get("primary_category")}),
                         "occurrences": len(members), "independent_threads": len(threads), "thread_ids": threads,
                         "event_at_min": min(item.get("event_at", "") for item in members), "event_at_max": max(item.get("event_at", "") for item in members),
                         "flags": sorted(set(flags)), "disposition": disposition, "items": members})
    families.sort(key=lambda row: (-row["independent_threads"], -row["occurrences"], row["family_key"]))
    return {"schema": "guidance.codex-family-audit.v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "input_items": len(items), "families": len(families),
            "reviewable_general": sum(row["disposition"] == "codex_reviewable_general_pattern" for row in families),
            "reviewable_question_rewrite": sum(row["disposition"] == "codex_reviewable_after_question_rewrite" for row in families),
            "held": sum(row["disposition"] == "held" for row in families),
            "flag_counts": dict(Counter(flag for row in families for flag in row["flags"])), "items": families,
            "boundary": "No active publication. Every reviewable family still requires original Hindsight source witness, canonical text review, conflict/staleness review and publication gate."}


def main(input_path: str | Path, output_path: str | Path):
    source = json.loads(Path(input_path).read_text()); result = audit(source.get("items") or [])
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2));
    print(json.dumps({key: result[key] for key in ("input_items", "families", "reviewable_general", "reviewable_question_rewrite", "held", "flag_counts")}, ensure_ascii=False))
