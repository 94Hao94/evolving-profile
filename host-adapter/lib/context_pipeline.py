"""Model-agnostic Context summarisation and review queue.

This module prepares auditable Luna/Sol work items. It never labels a seed as
model-reviewed without an explicit result carrying source IDs and a revision.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .context_summary import BUDGETS, bounded_summary


PIPELINE_SCHEMA = "evolving-profile.context-pipeline.v1"


def prepare_jobs(index: dict) -> dict:
    jobs = []
    for row in list(index.get("sessions") or []) + list(index.get("projects") or []):
        context_type = row.get("context_type")
        context_id = row.get("context_id")
        if context_type not in BUDGETS or not context_id:
            continue
        source_ids = list(row.get("source_ids") or [])
        summary = row.get("summary") or {}
        seed = str(summary.get("full") or summary.get("standard") or summary.get("compact") or "")
        needs_sol = bool(row.get("conflicts") or len(seed) > BUDGETS[context_type]["standard"]["max_chars"])
        jobs.append({
            "job_id": f"{context_id}:summary",
            "context_id": context_id,
            "context_type": context_type,
            "source_ids": source_ids,
            "input_text": seed,
            "target_tiers": ["compact", "standard", "full"],
            "primary_model": "gpt-6-luna-light-reasoning",
            "review_model": "gpt-6-sol-medium-reasoning" if needs_sol else None,
            "review_required": needs_sol,
            "status": "queued",
            "max_attempts": 5,
            "retry_policy": "exponential_backoff_idempotent",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "evidence_role": "context_navigation_only",
        })
    return {"schema": PIPELINE_SCHEMA, "status": "queued", "jobs": jobs,
            "execution_owner": "codex_agent_side",
            "mode": "one_off_historical_backfill_exception",
            "model_policy": {
                "batch": "gpt-6-luna-light-reasoning",
                "review": "gpt-6-sol-medium-reasoning",
                "external_ep_retrieval": "coding-plan-qwen3.7-plus",
                "coding_plan_for_context_summary": "not_used",
                "steady_state_context_summary": "ep_connected_model",
            }}


def apply_model_result(row: dict, result: dict) -> dict:
    """Validate an adapter result before publishing derived summaries."""
    if not isinstance(result, dict) or result.get("context_id") != row.get("context_id"):
        raise ValueError("context_result_identity_mismatch")
    if set(row.get("source_ids") or []) - set(result.get("source_ids") or []):
        raise ValueError("context_result_dropped_provenance")
    if result.get("status") not in {"model_generated", "model_reviewed"}:
        raise ValueError("context_result_not_reviewable")
    context_type = row.get("context_type")
    summaries = {}
    receipts = {}
    for tier in ("compact", "standard", "full"):
        summaries[tier], receipts[tier] = bounded_summary(
            (result.get("summaries") or {}).get(tier, ""), context_type, tier
        )
    published = dict(row)
    published.update({
        "summary": summaries,
        "summary_budget": receipts,
        "status": result["status"],
        "summary_model": result.get("summary_model") or row.get("primary_model"),
        "review_model": result.get("review_model"),
        "reviewed_at": result.get("reviewed_at"),
        "source_ids": list(row.get("source_ids") or []),
    })
    return published


def promote_session_draft(row: dict, source: dict, draft: dict, review: dict, manual: dict) -> dict:
    """Publish one reviewed conversation summary without upgrading it to Bank fact."""
    from .scenario_model import fingerprint_draft, review_chunk_limit_for_draft, validate_session_draft

    context_id = "session:" + str(source.get("thread_id") or "")
    revision = source.get("source_revision")
    draft_hash = fingerprint_draft(draft)
    if (row.get("context_type") != "session" or row.get("context_id") != context_id
            or source.get("status") != "complete" or not revision
            or draft.get("context_id") != context_id or draft.get("status") != "source_linked_draft"
            or draft.get("source_revision") != revision or draft.get("source_files") != source.get("source_files")
            or review.get("status") != "model_review_passed" or review.get("source_revision") != revision
            or review.get("issues") != [] or review.get("draft_sha256") != draft_hash
            or manual.get("verdict") != "conversation_only_draft_acceptable"
            or manual.get("source_revision") != revision or manual.get("draft_sha256") != draft_hash):
        raise ValueError("scenario_promotion_gate_failed")
    validated_draft = validate_session_draft(source, draft,
                                             model=str(draft.get("summary_model") or "unknown"))
    if draft.get("schema") == "evolving-profile.scenario-draft.v3":
        if (manual.get("scope_verdict") != "whole_session_scope_acceptable"
                or type(manual.get("reviewed_source_message_count")) is not int
                or manual.get("reviewed_source_message_count") != len(source["messages"])):
            raise ValueError("scenario_promotion_coverage_unresolved")
        selection_coverage = validated_draft.get("selection_coverage") or {}
        expected_chunks = selection_coverage.get("source_chunk_count", 1)
        review_coverage = review.get("review_coverage")
        expected_chunk_limit = review_chunk_limit_for_draft(draft, 30000)
        if type(expected_chunks) is not int or expected_chunks < 1:
            raise ValueError("scenario_promotion_review_coverage_incomplete")
        if expected_chunks > 1 and (not isinstance(review_coverage, dict)
                or review_coverage.get("source_chunk_count") != expected_chunks
                or review_coverage.get("source_chunk_char_limit") != expected_chunk_limit
                or review_coverage.get("reviewed_chunk_count") != expected_chunks
                or review_coverage.get("all_chunks_accepted") is not True
                or type(review_coverage.get("cross_chunk_claim_count")) is not int
                or type(review_coverage.get("cross_chunk_claim_reviewed_count")) is not int
                or review_coverage.get("cross_chunk_claim_reviewed_count")
                    != review_coverage.get("cross_chunk_claim_count")
                or type(review_coverage.get("unreviewed_cross_chunk_claim_count")) is not int
                or review_coverage["unreviewed_cross_chunk_claim_count"] != 0):
            raise ValueError("scenario_promotion_review_coverage_incomplete")
        if isinstance(review_coverage, dict):
            cross_count = review_coverage.get("cross_chunk_claim_count")
            reviewed_count = review_coverage.get("cross_chunk_claim_reviewed_count")
            unreviewed_count = review_coverage.get("unreviewed_cross_chunk_claim_count")
            if (type(cross_count) is not int or type(reviewed_count) is not int
                    or type(unreviewed_count) is not int or cross_count < 0
                    or reviewed_count != cross_count or unreviewed_count != 0
                    or (expected_chunks == 1 and cross_count != 0)):
                raise ValueError("scenario_promotion_review_coverage_incomplete")
        episode_scope = manual.get("episode_scope_verdict")
        if episode_scope == "multiple_topics":
            raise ValueError("scenario_promotion_episode_split_required")
        if episode_scope is None:
            raise ValueError("scenario_promotion_episode_scope_unresolved")
        if not isinstance(episode_scope, str):
            raise ValueError("scenario_promotion_episode_scope_invalid")
        if episode_scope in {"", "uncertain", "unresolved"}:
            raise ValueError("scenario_promotion_episode_scope_unresolved")
        if episode_scope != "single_coherent_task":
            raise ValueError("scenario_promotion_episode_scope_invalid")
    if draft.get("schema") == "evolving-profile.scenario-draft.v3":
        tiers = draft.get("summaries") or {}
        if " ".join(str(tiers.get("compact") or "").split()) == " ".join(str(tiers.get("full") or "").split()):
            raise ValueError("scenario_promotion_layers_not_distinct")
    result = {"context_id": context_id, "source_ids": row.get("source_ids") or [],
              "status": "model_reviewed", "summaries": draft.get("summaries") or {},
              "summary_model": draft.get("summary_model"),
              "review_model": review.get("review_model"),
              "reviewed_at": manual.get("reviewed_at") or datetime.now(timezone.utc).isoformat()}
    published = apply_model_result(row, result)
    if draft.get("schema") == "evolving-profile.scenario-draft.v3":
        published["scenario_state"] = draft["state"]
    if any(receipt["truncated"] or not published["summary"][tier]
           for tier, receipt in published["summary_budget"].items()):
        raise ValueError("scenario_promotion_budget_failed")
    published.update({"source_revision": revision, "raw_source_files": list(source["source_files"]),
                      "source_message_count": len(source["messages"]),
                      "review_scope": "conversation_only_not_external_fact_verification",
                      "manual_reviewer": manual.get("reviewer") or "unknown",
                      "updated_at": source["messages"][-1].get("at") or row.get("updated_at")})
    first_line = str((row.get('summary') or {}).get('compact') or '').split('\n', 1)[0].strip()
    if row.get('title') or first_line.startswith('# '):
        published['title'] = str(row.get('title') or first_line[2:].strip())[:120]
    if draft.get('selection_coverage'):
        published['selection_coverage'] = draft['selection_coverage']
    if draft.get("schema") == "evolving-profile.scenario-draft.v3":
        published["manual_source_coverage"] = {
            "scope_verdict": manual["scope_verdict"],
            "reviewed_source_message_count": manual["reviewed_source_message_count"],
            "episode_scope_verdict": manual["episode_scope_verdict"],
        }
    return published


def promote_episode_bundle(row: dict, source: dict, bundle: dict, review: dict, manual: dict) -> dict:
    """Publish a manually accepted multi-topic directory with isolated episode bodies."""
    from .scenario_episodes import validate_episode_bundle
    from .scenario_model import (fingerprint_draft, fingerprint_episode_bundle,
                                 review_chunk_limit_for_draft)

    context_id = "session:" + str(source.get("thread_id") or "")
    revision = source.get("source_revision")
    if (not isinstance(row, dict) or row.get("context_type") != "session"
            or row.get("context_id") != context_id or source.get("status") != "complete"
            or not revision or not isinstance(manual, dict)):
        raise ValueError("scenario_promotion_gate_failed")

    bundle = validate_episode_bundle(source, bundle)
    episodes = bundle["episodes"]
    episode_ids = [item["episode_id"] for item in episodes]
    if len(episodes) < 2:
        raise ValueError("scenario_promotion_episode_split_required")
    bundle_hash = fingerprint_episode_bundle(bundle)
    if (manual.get("verdict") != "conversation_only_draft_acceptable"
            or manual.get("source_revision") != revision
            or manual.get("draft_sha256") != bundle_hash):
        raise ValueError("scenario_promotion_gate_failed")
    if (manual.get("scope_verdict") != "whole_session_scope_acceptable"
            or type(manual.get("reviewed_source_message_count")) is not int
            or manual.get("reviewed_source_message_count") != len(source["messages"])):
        raise ValueError("scenario_promotion_coverage_unresolved")
    if manual.get("episode_scope_verdict") != "multiple_topics":
        raise ValueError("scenario_promotion_episode_split_required")
    if (manual.get("episode_partition_verdict") != "exact_contiguous_partition_acceptable"
            or manual.get("reviewed_episode_ids") != episode_ids):
        raise ValueError("scenario_episode_partition_review_unresolved")

    if (not isinstance(review, dict) or review.get("schema") != "evolving-profile.scenario-episode-review.v1"
            or review.get("status") != "model_review_passed"
            or review.get("thread_id") != source["thread_id"]
            or review.get("parent_source_revision") != revision
            or review.get("bundle_sha256") != bundle_hash
            or review.get("reviewed_episode_ids") != episode_ids
            or review.get("issues") != []
            or not isinstance(review.get("episode_reviews"), list)
            or len(review["episode_reviews"]) != len(episodes)):
        raise ValueError("scenario_episode_review_failed")

    episode_reviews = review["episode_reviews"]
    published_episodes = []
    for episode, episode_review in zip(episodes, episode_reviews):
        draft = episode["draft"]
        if (not isinstance(episode_review, dict)
                or episode_review.get("episode_id") != episode["episode_id"]
                or episode_review.get("status") != "model_review_passed"
                or episode_review.get("source_revision") != episode["source_revision"]
                or episode_review.get("draft_sha256") != fingerprint_draft(draft)
                or episode_review.get("issues") != []):
            raise ValueError("scenario_episode_review_failed")
        coverage = episode_review.get("review_coverage")
        selection_coverage = draft.get("selection_coverage") or {}
        expected_chunks = selection_coverage.get("source_chunk_count", 1)
        expected_chunk_limit = review_chunk_limit_for_draft(draft, 30000)
        if type(expected_chunks) is not int or expected_chunks < 1:
            raise ValueError("scenario_episode_review_coverage_incomplete")
        if expected_chunks > 1 and (not isinstance(coverage, dict)
                or coverage.get("source_chunk_count") != expected_chunks
                or coverage.get("source_chunk_char_limit") != expected_chunk_limit
                or coverage.get("reviewed_chunk_count") != expected_chunks
                or coverage.get("all_chunks_accepted") is not True
                or type(coverage.get("cross_chunk_claim_count")) is not int
                or type(coverage.get("cross_chunk_claim_reviewed_count")) is not int
                or coverage.get("cross_chunk_claim_reviewed_count") != coverage.get("cross_chunk_claim_count")
                or type(coverage.get("unreviewed_cross_chunk_claim_count")) is not int
                or coverage["unreviewed_cross_chunk_claim_count"] != 0):
            raise ValueError("scenario_episode_review_coverage_incomplete")
        if isinstance(coverage, dict):
            cross_count = coverage.get("cross_chunk_claim_count")
            reviewed_count = coverage.get("cross_chunk_claim_reviewed_count")
            unreviewed_count = coverage.get("unreviewed_cross_chunk_claim_count")
            if (type(cross_count) is not int or type(reviewed_count) is not int
                    or type(unreviewed_count) is not int or cross_count < 0
                    or reviewed_count != cross_count or unreviewed_count != 0
                    or (expected_chunks == 1 and cross_count != 0)):
                raise ValueError("scenario_episode_review_coverage_incomplete")
        if (isinstance(coverage, dict)
                and type(coverage.get("unreviewed_cross_chunk_claim_count")) is int
                and coverage["unreviewed_cross_chunk_claim_count"] > 0):
            raise ValueError("scenario_episode_review_coverage_incomplete")
        summaries = {}
        budgets = {}
        for tier in ("compact", "standard", "full"):
            summaries[tier], budgets[tier] = bounded_summary(draft["summaries"].get(tier, ""), "session", tier)
        compact = " ".join(summaries["compact"].split())
        full = " ".join(summaries["full"].split())
        if (not compact or compact == full
                or any(not summaries[tier] or budgets[tier]["truncated"] for tier in summaries)):
            raise ValueError("scenario_promotion_layers_not_distinct")
        published_episodes.append({
            "episode_id": episode["episode_id"], "parent_session_id": source["thread_id"],
            "parent_source_revision": revision, "source_revision": episode["source_revision"],
            "title": episode["title"], "title_authority": episode["title_authority"],
            "start_message_id": episode["start_message_id"],
            "start_user_message_id": episode["start_user_message_id"],
            "end_message_id": episode["end_message_id"],
            "message_ids": list(episode["message_ids"]),
            "source_message_count": episode["source_message_count"],
            "source_file_ids": list(episode.get("source_file_ids") or []),
            "source_offsets": list(episode.get("source_offsets") or []),
            "summary": summaries, "summary_budget": budgets,
            "scenario_state": draft["state"], "unknowns": list(draft.get("unknowns") or []),
            "summary_model": draft.get("summary_model"),
            "review_model": episode_review.get("review_model"),
            "reviewed_at": review.get("reviewed_at"),
            "status": "model_reviewed",
            "review_scope": "episode_only_against_exact_source_span_not_external_fact_verification",
            "evidence_role": "context_navigation_only",
        })

    directory = {
        "compact": f"人工复核确认这是多主题 Session，包含 {len(episodes)} 个 episode；按 episode_id 选择单段读取。",
        "standard": f"多主题 Session 目录，共 {len(episodes)} 个独立来源段。父节点不合并各段正文；选定 episode_id 后再读取对应三级摘要。",
        "full": f"该目录只负责情景导航，不是 Bank 事实。每个 episode 保留独立消息范围和来源修订；需要原文证据时继续按来源定位回读。",
    }
    result = {"context_id": context_id, "source_ids": row.get("source_ids") or [],
              "status": "model_reviewed", "summaries": directory,
              "summary_model": episodes[0]["draft"].get("summary_model"),
              "review_model": review.get("review_model"), "reviewed_at": review.get("reviewed_at")}
    published = apply_model_result(row, result)
    published.update({"status": "episode_directory_ready", "episodes": published_episodes,
                      "source_revision": revision, "raw_source_files": list(source["source_files"]),
                      "source_message_count": len(source["messages"]),
                      "manual_source_coverage": {
                          "scope_verdict": manual["scope_verdict"],
                          "reviewed_source_message_count": manual["reviewed_source_message_count"],
                          "episode_scope_verdict": manual["episode_scope_verdict"],
                          "episode_partition_verdict": manual["episode_partition_verdict"],
                          "reviewed_episode_ids": list(manual["reviewed_episode_ids"]),
                      },
                      "episode_boundary_decisions": list(bundle["boundary_decisions"]),
                      "episode_partition_status": "exact_contiguous_partition_manually_reviewed",
                      "review_scope": "whole_source_partition_manually_reviewed; episode_summaries_model_reviewed_not_external_fact_verification",
                      "manual_reviewer": manual.get("reviewer") or "unknown",
                      "updated_at": source["messages"][-1].get("at") or row.get("updated_at")})
    published.pop("scenario_state", None)
    return published


def write_queue(path: str | os.PathLike, queue: dict) -> dict:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(queue, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        try:
            os.unlink(temp)
        except FileNotFoundError:
            pass
    return {"ok": True, "path": str(target), "job_count": len(queue.get("jobs") or [])}


def progress_snapshot(queue: dict, receipts: list[dict] | None = None) -> dict:
    counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "retrying": 0}
    for job in queue.get("jobs") or []:
        status = str(job.get("status") or "queued")
        if status in counts:
            counts[status] += 1
        else:
            counts["queued"] += 1
    for receipt in receipts or []:
        job_id = receipt.get("job_id")
        for job in queue.get("jobs") or []:
            if job.get("job_id") == job_id:
                old = str(job.get("status") or "queued")
                if old in counts: counts[old] = max(0, counts[old] - 1)
                new = str(receipt.get("status") or "failed")
                counts["retrying" if new == "retrying" else new if new in counts else "failed"] += 1
                break
    total = len(queue.get("jobs") or [])
    return {"schema": "evolving-profile.context-progress.v1", "status": "running" if counts["running"] or counts["retrying"] else "queued", "total": total, **counts}


def write_progress(path: str | os.PathLike, snapshot: dict) -> dict:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=target.name + ".", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({**snapshot, "updated_at": datetime.now(timezone.utc).isoformat()}, handle, ensure_ascii=False, indent=2)
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        try: os.unlink(temp)
        except FileNotFoundError: pass
    return {"ok": True, "path": str(target)}
