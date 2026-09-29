#!/usr/bin/env python3
"""Create source-linked Session episode drafts without publishing them."""

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
from lib.scenario_model import (fingerprint_episode_bundle, request_episode_bundle,
                                safe_validation_error_code)
from lib.scenario_source import read_session_source
from observation_rebuild import atomic, load_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", action="append", required=True)
    parser.add_argument("--session-root", default=str(Path.home() / ".codex/sessions"))
    parser.add_argument("--index", default=str(Path.home() / ".evolving-profile/context/context-index.json"))
    parser.add_argument("--output-dir", default=str(Path.home() / ".evolving-profile/context/pilot-episode-drafts"))
    parser.add_argument("--max-chars", type=int, default=500000,
                        help="Total visible source safety bound; model input is chunked separately")
    parser.add_argument("--chunk-chars", type=int, default=30000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    index = read_context_index(args.index)
    known = {str(row.get("session_id")) for row in index.get("sessions") or []}
    config = None
    items = []
    output_dir = Path(args.output_dir).expanduser()

    for thread_id in dict.fromkeys(args.session_id):
        if thread_id not in known:
            items.append({"session_id": thread_id, "status": "not_in_context_index"})
            continue
        source = read_session_source(thread_id, args.session_root, max_chars=args.max_chars)
        receipt = {"session_id": thread_id, "source": source["source"],
                   "source_status": source["status"], "source_messages": len(source["messages"]),
                   "source_chars": source["total_chars"], "source_revision": source["source_revision"]}
        if source["status"] != "complete":
            items.append({**receipt, "status": "source_not_ready"})
            continue
        if args.dry_run:
            items.append({**receipt, "status": "source_ready"})
            continue

        marker = output_dir / ".attempts" / ("episode-" + thread_id + ".json")
        atomic(marker, {"status": "pending", "source_revision": source["source_revision"]})
        try:
            if config is None:
                config = load_env()
        except (OSError, ValueError, KeyError, TypeError):
            atomic(marker, {"status": "failed", "source_revision": source["source_revision"],
                            "error_code": "provider_configuration_unavailable"})
            items.append({**receipt, "status": "model_failed", "error_code": "provider_configuration_unavailable"})
            continue

        validation_code = None

        def generate(_attempt):
            nonlocal validation_code
            try:
                return request_episode_bundle(
                    source,
                    base_url=config["EVOLVING_PROFILE_API_LLM_BASE_URL"],
                    api_key=config["EVOLVING_PROFILE_API_LLM_API_KEY"],
                    model=config["EVOLVING_PROFILE_API_LLM_MODEL"],
                    max_input_chars=args.chunk_chars,
                )
            except ValueError as error:
                validation_code = safe_validation_error_code(error)
                raise
            except urllib.error.URLError as error:
                raise ConnectionError("scenario_episode_model_transport_failed") from error

        attempt = run_with_retry(generate, max_attempts=3, base_delay=2)
        if attempt["status"] != "succeeded":
            error_code = validation_code or attempt.get("error") or "unknown"
            atomic(marker, {"status": "failed", "source_revision": source["source_revision"],
                            "error_code": error_code})
            items.append({**receipt, "status": "model_failed", "attempts": attempt["attempt"],
                          "error_code": error_code})
            continue

        bundle = attempt["result"]
        target = output_dir / (thread_id + ".json")
        atomic(target, bundle)
        digest = fingerprint_episode_bundle(bundle)
        atomic(marker, {"status": "succeeded", "source_revision": source["source_revision"],
                        "draft_sha256": digest})
        items.append({**receipt, "status": bundle["status"], "draft_path": str(target),
                      "episode_count": len(bundle.get("episodes") or []),
                      "episode_ids": [row.get("episode_id") for row in bundle.get("episodes") or []],
                      "draft_sha256": digest,
                      "unresolved_boundary_count": len(bundle.get("unresolved_boundary_ids") or []),
                      "attempts": attempt["attempt"]})

    print(json.dumps({"schema": "evolving-profile.episode-pilot-receipt.v1",
                      "dry_run": args.dry_run, "items": items}, ensure_ascii=False))
    accepted = {"source_ready"} if args.dry_run else {
        "source_linked_episode_draft", "episode_boundary_unresolved"}
    return 1 if any(item["status"] not in accepted for item in items) else 0


if __name__ == "__main__":
    raise SystemExit(main())
