"""Replay recent prompt receipts into a selector-evaluation report."""
from __future__ import annotations

import json
from pathlib import Path

from mcp_runtime import load_repository
from selector import get_task_guidance


def replay(receipts: list[dict], repo, limit: int = 50) -> dict:
    cases = []
    for row in receipts[:limit]:
        receipt = row.get("guidance_receipt") or {}
        prompt = str(row.get("user_prompt") or row.get("prompt") or "")
        task = receipt.get("task") or {
            "objective": prompt,
            "current_user_message": prompt,
            "context_summary": "",
            "previous_user_messages": [],
            "continuation": False,
            "phase": "analyze",
            "current_constraints": [],
            "domains": [],
            "media": ["text"],
            "resolved_entities": [],
            "unresolved_references": [],
        }
        result = get_task_guidance(repo, {"task": task, "loaded": [], "memory_policy": "allowed"}, char_budget=10000)
        cases.append({"prompt_id": row.get("prompt_id"), "prompt": prompt,
                      "expected": [], "selected": [item.get("id") for item in result.get("included", [])],
                      "selection_revision": result.get("selection_revision"), "coverage": result.get("coverage"),
                      "label_state": "awaiting_human_expected_labels"})
    return {"schema": "evolving-profile.selector-replay.v1", "limit": limit, "cases": cases,
            "boundary": "selected is deterministic replay output; expected is intentionally empty until human annotation; no registry mutation"}


def main(receipt_path: str, output_path: str, registry: str, bank_id: str):
    receipts = json.loads(Path(receipt_path).read_text())
    if isinstance(receipts, dict):
        receipts = receipts.get("items") or receipts.get("cases") or []
    repo = load_repository(registry)
    Path(output_path).write_text(json.dumps(replay(receipts, repo), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(); parser.add_argument("receipts"); parser.add_argument("output"); parser.add_argument("registry"); parser.add_argument("bank_id")
    args = parser.parse_args(); main(args.receipts, args.output, args.registry, args.bank_id)
