"""Shadow inventory for final assistant messages.

This deliberately does not change the current Bank retain payload.  It records
only enough metadata to later compare selective assistant retention against the
existing policy and re-read the authoritative host transcript when needed.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_ELIGIBLE_CATEGORIES = frozenset({"proposal", "artifact", "tool_verified_result"})


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def classify_final_answer(text: str) -> dict[str, Any]:
    """Classify one final answer conservatively without asserting user acceptance."""
    value = str(text or "").strip()
    lowered = value.casefold()
    has_verification = any(marker in value for marker in ("验证", "测试", "回读", "核验", "检查"))
    has_success = any(marker in value for marker in ("通过", "成功", "完成", "已修复", "已部署"))
    has_artifact = any(marker in value for marker in ("文件", "产物", "文档", ".py", ".md", ".json", ".tsx"))
    has_proposal = any(marker in value for marker in ("建议", "推荐", "方案", "可选", "取舍"))

    if has_verification and has_success:
        category = "tool_verified_result"
        reason = "verification_and_result_language"
    elif has_artifact:
        category = "artifact"
        reason = "versioned_artifact_or_path_language"
    elif has_proposal:
        category = "proposal"
        reason = "proposal_language"
    elif any(marker in lowered for marker in ("已完成", "完成了", "已经处理", "已修复")):
        category = "assistant_claim"
        reason = "claim_without_verifiable_receipt"
    else:
        category = "boilerplate"
        reason = "no_selective_retention_signal"

    return {
        "category": category,
        "reason": reason,
        "eligible_for_shadow_semantic_extraction": category in _ELIGIBLE_CATEGORIES,
    }


def record_final_answer_shadow(
    messages: list[Mapping[str, Any]], state_root: Path, session_id: str, project: str
) -> dict[str, Any]:
    """Append deduplicated final-answer metadata without copying the answer text."""
    root = Path(state_root) / "memory-os" / "assistant-retention-shadow"
    manifests = root / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    session_hash = _sha256(str(session_id or "unknown"))[:20]
    manifest_path = manifests / f"{session_hash}.json"
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = {"schema": "assistant-retention-shadow.v1", "session_id": str(session_id), "items": []}
    if not isinstance(existing, dict) or not isinstance(existing.get("items"), list):
        existing = {"schema": "assistant-retention-shadow.v1", "session_id": str(session_id), "items": []}

    known_ids = {str(item.get("id")) for item in existing["items"] if isinstance(item, dict)}
    categories: Counter[str] = Counter()
    recorded = 0
    for index, message in enumerate(messages or []):
        if str(message.get("role") or "").casefold() != "assistant":
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        source_record = message.get("source_record") if isinstance(message.get("source_record"), Mapping) else {}
        content_sha256 = _sha256(content)
        item_id = _sha256(
            "\0".join((str(session_id), str(index), content_sha256, str(source_record.get("raw_line_sha256") or "")))
        )
        if item_id in known_ids:
            continue
        classification = classify_final_answer(content)
        categories[classification["category"]] += 1
        existing["items"].append(
            {
                "id": item_id,
                "content_sha256": content_sha256,
                "content_chars": len(content),
                "source_record": dict(source_record),
                "project": str(project or "unknown"),
                "classification": classification,
            }
        )
        known_ids.add(item_id)
        recorded += 1

    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(existing, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, manifest_path)
    return {
        "recorded": recorded,
        "categories": dict(categories),
        "manifest_path": str(manifest_path),
        "mode": "shadow_only_no_bank_payload_change",
    }
