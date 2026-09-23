"""Consolidate Codex-reviewed raw families against active preference text."""
from __future__ import annotations

from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re


STOP = set("的了是我你他她它和与在这那一个一些以后现在当前需要应该可以不能不要必须通过进行以及然后因为如果如何什么对于其中相关内容问题方式要求说明检查测试整体之前新的原来的" )


def tokens(value: str) -> set[str]:
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", str(value or "").casefold())
    words = set()
    for word in value.split():
        if len(word) > 1: words.add(word)
        if len(word) >= 2:
            words.update(word[i:i+2] for i in range(len(word)-1))
    return {word for word in words if word not in STOP}


def similarity(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    return len(a & b) / max(1, len(a | b))


def classify(candidate: dict, active: list[dict]) -> dict:
    text = candidate.get("canonical_text") or candidate.get("verbatim_quote") or ""
    best = max(((similarity(text, unit.get("text", "")), index, unit) for index, unit in enumerate(active)), default=(0, 0, None)) if active else (0, 0, None)
    score, _, unit = best
    flags = set(candidate.get("flags") or [])
    if candidate.get("disposition") == "codex_reviewable_after_question_rewrite":
        state = "question_or_test_prompt"
    elif "local_scope_signal" in flags or candidate.get("scope_level") in {"task", "project"}:
        state = "task_local"
    elif "method_or_volatile_claim" in flags:
        state = "method_needs_validation"
    elif score >= 0.15:
        state = "existing_preference_reinforcement"
    elif candidate.get("independent_threads", 0) >= 2 and candidate.get("scope_level") == "global":
        state = "new_preference_candidate"
    else:
        state = "needs_semantic_review"
    return {"family_key": candidate.get("family_key"), "canonical_text": text, "state": state,
            "similarity_to_active": round(score, 4), "nearest_active_id": unit.get("id") if unit else None,
            "nearest_active_text": unit.get("text") if unit else None, "candidate": candidate}


def consolidate(raw_path: str | Path, active_path: str | Path, output_path: str | Path) -> dict:
    raw = json.loads(Path(raw_path).read_text()); active = json.loads(Path(active_path).read_text()).get("items", [])
    rows = [classify(candidate, active) for candidate in raw.get("items", []) if candidate.get("disposition") != "held"]
    result = {"schema": "guidance.codex-candidate-consolidation.v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "raw_families": len(rows), "state_counts": dict(Counter(row["state"] for row in rows)), "items": rows,
              "boundary": "No registry mutation. New candidates require source UUID witness, canonical ASR review, conflict/staleness review and controlled publication."}
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2)); print(json.dumps({"raw_families":len(rows),"state_counts":result["state_counts"]},ensure_ascii=False)); return result


if __name__ == "__main__":
    import sys
    consolidate(sys.argv[1], sys.argv[2], sys.argv[3])
