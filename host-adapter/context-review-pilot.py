#!/usr/bin/env python3
"""Review private Session Scenario Summary drafts against original conversation text."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, os.environ.get("EVOLVING_PROFILE_GUIDANCE_SRC", str(HERE.parent / "guidance")))

from lib.context_retry import run_with_retry
from lib.context_summary import read_context_index
from lib.scenario_model import (request_session_review, safe_validation_error_code, fingerprint_draft,
                                review_chunk_limit_for_draft, validate_latest_v3_attempt)
from lib.scenario_source import read_session_source
from observation_rebuild import atomic, load_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", action="append", required=True)
    parser.add_argument("--session-root", default=str(Path.home() / ".codex/sessions"))
    parser.add_argument("--index", default=str(Path.home() / ".evolving-profile/context/context-index.json"))
    parser.add_argument("--draft-dir", default=str(Path.home() / ".evolving-profile/context/pilot-drafts"))
    parser.add_argument("--output-dir", default=str(Path.home() / ".evolving-profile/context/pilot-reviews"))
    parser.add_argument("--max-chars", type=int, default=500000)
    parser.add_argument("--chunk-chars", type=int, default=30000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    index = read_context_index(args.index)
    known = {str(row.get("session_id")) for row in index.get("sessions") or []}
    config = None
    items = []

    def persist_failure(source, reason, draft=None, status='model_review_failed'):
        if args.dry_run:
            return
        atomic(Path(args.output_dir).expanduser() / (source['thread_id'] + '.json'), {
            'schema': 'evolving-profile.scenario-review.v1', 'context_id': 'session:' + source['thread_id'],
            'status': status, 'failure_reason': reason,
            'source_revision': source.get('source_revision'),
            'draft_sha256': fingerprint_draft(draft) if isinstance(draft, dict) else None,
            'issues': [], 'review_scope': 'latest_attempt_failed_not_publishable',
        })
    for thread_id in dict.fromkeys(args.session_id):
        if thread_id not in known:
            items.append({"session_id": thread_id, "status": "not_in_context_index"})
            continue
        source = read_session_source(thread_id, args.session_root, max_chars=args.max_chars)
        receipt = {"session_id": thread_id, "source": source["source"],
                   "source_status": source["status"], "source_revision": source["source_revision"]}
        if source["status"] != "complete":
            persist_failure(source, 'source_not_ready')
            items.append({**receipt, "status": "source_not_ready"})
            continue
        target = Path(args.draft_dir).expanduser() / (source["thread_id"] + ".json")
        try:
            draft = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            persist_failure(source, 'draft_missing')
            items.append({**receipt, "status": "draft_missing"})
            continue
        if not isinstance(draft, dict):
            persist_failure(source, 'draft_invalid')
            items.append({**receipt, 'status': 'draft_invalid'})
            continue
        if draft.get("source_revision") != source["source_revision"]:
            persist_failure(source, 'draft_stale', draft)
            items.append({**receipt, "status": "draft_stale"})
            continue
        if draft.get("schema") == "evolving-profile.scenario-draft.v3":
            try:
                validate_latest_v3_attempt(args.draft_dir, thread_id, draft, source["source_revision"])
            except ValueError:
                persist_failure(source, 'draft_latest_attempt_not_successful', draft)
                items.append({**receipt, "status": "draft_latest_attempt_not_successful"})
                continue
        if args.dry_run:
            items.append({**receipt, "status": "source_ready"})
            continue

        persist_failure(source, 'review_attempt_started', draft, status='model_review_pending')
        try:
            if config is None:
                config = load_env()
        except (OSError, ValueError, KeyError, TypeError):
            persist_failure(source, 'provider_configuration_unavailable', draft)
            items.append({**receipt, 'status': 'review_failed', 'error_code': 'provider_configuration_unavailable'})
            continue

        validation_code = None

        def review(_attempt):
            nonlocal validation_code
            try:
                review_chunk_chars = review_chunk_limit_for_draft(draft, args.chunk_chars)
                return request_session_review(source, draft,
                    base_url=config["EVOLVING_PROFILE_API_LLM_BASE_URL"],
                    api_key=config["EVOLVING_PROFILE_API_LLM_API_KEY"],
                    model=config["EVOLVING_PROFILE_API_LLM_MODEL"], max_input_chars=review_chunk_chars)
            except ValueError as error:
                validation_code = safe_validation_error_code(error)
                raise
            except urllib.error.URLError as error:
                raise ConnectionError("scenario_review_transport_failed") from error

        attempt = run_with_retry(review, max_attempts=3, base_delay=2)
        if attempt["status"] != "succeeded":
            persist_failure(source, validation_code or attempt.get('error') or 'unknown', draft)
            items.append({**receipt, "status": "review_failed", "attempts": attempt["attempt"],
                          "error_code": validation_code or attempt.get("error") or "unknown"})
            continue
        value = attempt["result"]
        output = Path(args.output_dir).expanduser() / (source["thread_id"] + ".json")
        atomic(output, value)
        items.append({**receipt, "status": value["status"], "review_path": str(output),
                      "issue_count": len(value["issues"]), "issue_codes": [issue["code"] for issue in value["issues"]],
                      "attempts": attempt["attempt"]})
    print(json.dumps({"schema": "evolving-profile.scenario-review-receipt.v1", "dry_run": args.dry_run,
                      "items": items}, ensure_ascii=False))
    accepted = {"source_ready"} if args.dry_run else {"model_review_passed", "model_review_rejected"}
    return 1 if any(item["status"] not in accepted for item in items) else 0


if __name__ == "__main__":
    raise SystemExit(main())
