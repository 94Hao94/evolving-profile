"""Event-time raw conversation inventory and preference candidate contracts.

Historical text is untrusted data. This module never treats it as current
instructions and never publishes by itself.
"""
from __future__ import annotations

import datetime as dt
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3


THREAD_DB = Path.home() / ".codex/thread_history_1.sqlite"
CATEGORIES = {"communication", "learning", "reasoning", "collaboration", "delivery"}
NATURES = {"explicit_requirement", "declared_preference", "inferred_pattern", "task_local"}
POLARITIES = {"prefer", "avoid", "require", "forbid", "neutral"}
SCOPE_LEVELS = {"global", "domain", "project", "task"}
VALIDITY_KINDS = {"stable", "context_sensitive", "volatile_method"}
NOISE = re.compile(r"^(?:好|好的|嗯|继续|收到|谢谢|ok|okay|是的|对|明白|可以)[。！!，, ]*$", re.I)
EXPLICIT_CORRECTION = re.compile(r"(?:不是.{1,32}(?:是|为)|(?:应|应该)(?:改|写|叫|是).{1,32})")
SIGNAL = re.compile(
    r"(?:偏好|喜欢|更喜欢|不喜欢|必须|一定|以后|不要|不能|禁止|优先|务必|严禁|只要|除非|"
    r"不对|错了|有问题|太乱|太少|太多|不满意|满意|应该|改成|换成|保留|删除|隐藏|沿用|"
    r"看不清|重叠|漏了|遗漏|风格|格式|结构|逻辑|建议|推荐|验证|测试|审核|审计|复盘|避免)", re.I
)
BLOCKS = [
    re.compile(r"<in-app-browser-context\b.*?</in-app-browser-context>", re.S | re.I),
    re.compile(r"<hindsight_memories\b.*?</hindsight_memories>", re.S | re.I),
    re.compile(r"<environment_context\b.*?</environment_context>", re.S | re.I),
    re.compile(r"<recommended_plugins\b.*?</recommended_plugins>", re.S | re.I),
    re.compile(r"\[TRAINER_TRANSACTION_CONTEXT\].*?\[/TRAINER_TRANSACTION_CONTEXT\]", re.S | re.I),
    re.compile(r"\[TRAINER_AUTOMATIC_NEXT_CONTEXT\].*?\[/TRAINER_AUTOMATIC_NEXT_CONTEXT\]", re.S | re.I),
]


def clean_user_text(text: str) -> str:
    """Remove generated host wrappers without correcting or paraphrasing user text."""
    value = str(text or "")
    for pattern in BLOCKS:
        value = pattern.sub("", value)
    if "# Files mentioned by the user:" in value and "## My request for Codex:" in value:
        value = value.split("## My request for Codex:", 1)[1]
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    return value


def extract_message_text(item_json: str | dict) -> str:
    value = json.loads(item_json) if isinstance(item_json, str) else item_json
    if not isinstance(value, dict) or value.get("type") != "userMessage":
        return ""
    parts = [row.get("text", "") for row in value.get("content") or []
             if isinstance(row, dict) and row.get("type") == "text"]
    return clean_user_text("\n".join(parts))


def reviewable_message(text: str) -> bool:
    value = re.sub(r"\s+", "", str(text or ""))
    if NOISE.fullmatch(value):
        return False
    if EXPLICIT_CORRECTION.search(value): return True
    if len(value) < 8: return False
    return bool(SIGNAL.search(value) or len(value) >= 80)


def validate_candidate(candidate: dict, source_text: str) -> dict:
    if not isinstance(candidate, dict) or candidate.get("disposition") != "candidate":
        return {"ok": False, "reason": "not_candidate"}
    if candidate.get("primary_category") not in CATEGORIES or candidate.get("nature") not in NATURES:
        return {"ok": False, "reason": "invalid_classification"}
    quote = str(candidate.get("verbatim_quote") or "")
    if not quote or quote not in source_text:
        return {"ok": False, "reason": "quote_not_verbatim"}
    if candidate.get("uncertain_terms"):
        return {"ok": False, "reason": "uncertain_high_risk_terms"}
    for correction in candidate.get("asr_corrections") or []:
        if not isinstance(correction, dict) or not correction.get("from") or not correction.get("to") or not correction.get("basis"):
            return {"ok": False, "reason": "invalid_asr_correction"}
        if correction["from"] not in quote or not isinstance(correction.get("confidence"), (int, float)):
            return {"ok": False, "reason": "unsupported_asr_correction"}
    for key in ("canonical_text", "applies_when", "exceptions", "effect_on_action", "scope"):
        if key not in candidate:
            return {"ok": False, "reason": "missing_candidate_field"}
    structured = (
        "preference_kind", "polarity", "scope_level", "validity_kind", "confidence_inputs",
        "support_count", "contradiction_count", "source_turn_ids", "source_family_ids",
        "supersedes", "superseded_by", "cross_cutting",
    )
    if any(key not in candidate for key in structured):
        return {"ok": False, "reason": "missing_structured_candidate_field"}
    if candidate["polarity"] not in POLARITIES or candidate["scope_level"] not in SCOPE_LEVELS or candidate["validity_kind"] not in VALIDITY_KINDS:
        return {"ok": False, "reason": "invalid_structured_candidate_classification"}
    if not isinstance(candidate["preference_kind"], str) or not candidate["preference_kind"].strip():
        return {"ok": False, "reason": "invalid_preference_kind"}
    if not isinstance(candidate["confidence_inputs"], dict):
        return {"ok": False, "reason": "invalid_confidence_inputs"}
    if any(not isinstance(candidate[key], int) or candidate[key] < 0 for key in ("support_count", "contradiction_count")):
        return {"ok": False, "reason": "invalid_evidence_counts"}
    if any(not isinstance(candidate[key], list) for key in ("source_turn_ids", "source_family_ids", "supersedes", "superseded_by")):
        return {"ok": False, "reason": "invalid_structured_candidate_list"}
    if not isinstance(candidate["cross_cutting"], bool):
        return {"ok": False, "reason": "invalid_cross_cutting"}
    if candidate["nature"] == "inferred_pattern" and candidate["support_count"] < 2 and candidate.get("publication_state") in {"reviewed_preference", "active_preference"}:
        return {"ok": False, "reason": "single_inferred_candidate_not_publishable"}
    return {"ok": True, "reason": "candidate_contract_valid"}


def iso_from_ms(value: int) -> str:
    return dt.datetime.fromtimestamp(value / 1000, dt.timezone.utc).isoformat()


def load_raw_messages(start: dt.datetime, end: dt.datetime, db_path: str | Path = THREAD_DB) -> list[dict]:
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    db = sqlite3.connect(db_path); db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT thread_id,turn_id,item_id,rollout_ordinal,created_at_ms,item_json "
            "FROM thread_items WHERE item_type='userMessage' AND created_at_ms>=? AND created_at_ms<? "
            "ORDER BY thread_id,rollout_ordinal", (start_ms, end_ms)).fetchall()
    finally:
        db.close()
    result = []
    for row in rows:
        text = extract_message_text(row["item_json"])
        if not text:
            continue
        result.append({"thread_id": row["thread_id"], "turn_id": row["turn_id"], "item_id": row["item_id"],
                       "rollout_ordinal": row["rollout_ordinal"], "created_at": iso_from_ms(row["created_at_ms"]),
                       "text": text, "source_sha256": sha256(text.encode()).hexdigest(),
                       "reviewable": reviewable_message(text)})
    return result


def write_inventory(start: dt.datetime, end: dt.datetime, output: str | Path, db_path: str | Path = THREAD_DB) -> dict:
    messages = load_raw_messages(start, end, db_path)
    report = {"schema": "guidance.raw-conversation-inventory.v2", "source": str(db_path),
              "event_time_start": start.isoformat(), "event_time_end": end.isoformat(),
              "messages": len(messages), "reviewable_messages": sum(row["reviewable"] for row in messages),
              "items": messages, "boundary": "inventory_only; no candidate or active preference created"}
    target = Path(output); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True); parser.add_argument("--end", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(write_inventory(dt.datetime.fromisoformat(args.start), dt.datetime.fromisoformat(args.end), args.output), ensure_ascii=False))
