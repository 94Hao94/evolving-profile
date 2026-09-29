import copy
import unittest

from lib.context_pipeline import promote_episode_bundle
from lib.context_summary import build_session_context
from lib.scenario_episodes import partition_source, validate_episode_bundle
from lib.scenario_model import fingerprint_draft, fingerprint_episode_bundle
from lib.scenario_source import revision_for_messages
from lib.scenario_state_v3 import validate_state_draft


THREAD_ID = "01a0aad3-d9dd-7400-b1e7-a636388cab3b"


def source():
    messages = []
    for index, (role, text, turn) in enumerate([
        ("user", "请编制项目甲方案", "t1"), ("assistant", "项目甲方案已完成", "t1"),
        ("user", "另一个任务：比较项目乙预算", "t2"), ("assistant", "项目乙预算已比较", "t2"),
    ], 1):
        messages.append({"evidence_id": f"id{index}", "model_ref": f"m{index}",
                         "role": role, "text": text, "turn_id": turn,
                         "at": f"2026-09-27T00:{index:02d}:00Z", "source_path": "rollout.jsonl",
                         "byte_offset": index * 100, "raw_line_sha256": f"raw-{index}"})
    return {"thread_id": THREAD_ID, "source": "codex_thread_history",
            "source_files": ["rollout.jsonl"], "status": "complete", "messages": messages,
            "source_revision": revision_for_messages(messages)}


def bundle_fixture(original=None):
    original = original or source()
    partitions = partition_source(original, ["id3"])
    episodes = []
    for part in partitions:
        subsource = {**original, "messages": part["_messages"], "source_revision": part["source_revision"]}
        user_id = next(row["evidence_id"] for row in part["_messages"] if row["role"] == "user")
        assistant_id = next(row["evidence_id"] for row in part["_messages"] if row["role"] == "assistant")
        draft = validate_state_draft(subsource, {
            "subject": {"text": f"{user_id} 对应的任务", "message_ids": [user_id]},
            "goal": {"text": "完成该段任务", "message_ids": [user_id]},
            "phase": "assistant_reported", "constraints": [], "corrections": [],
            "assistant_reports": [{"text": "助手报告已答复", "message_ids": [assistant_id]}],
            "unresolved": [],
        }, model="test-model")
        episodes.append({**{key: value for key, value in part.items() if key != "_messages"},
                         "title": draft["state"]["subject"]["text"],
                         "title_authority": "navigation_label_not_verified_fact", "draft": draft})
    return validate_episode_bundle(original, {
        "schema": "evolving-profile.scenario-episode-bundle.v1",
        "status": "source_linked_episode_draft", "thread_id": original["thread_id"],
        "parent_source_revision": original["source_revision"], "chunk_count": 1,
        "boundary_decisions": [{"message_id": "id3", "decision": "new_episode",
                                "method": "model_boundary_review"}],
        "unresolved_boundary_ids": [], "episodes": episodes,
        "partition_status": "exact_contiguous_partition_pending_manual_review",
        "evidence_role": "context_navigation_only",
    })


def review_fixture(bundle):
    return {"schema": "evolving-profile.scenario-episode-review.v1",
            "status": "model_review_passed", "thread_id": bundle["thread_id"],
            "parent_source_revision": bundle["parent_source_revision"],
            "bundle_sha256": fingerprint_episode_bundle(bundle),
            "reviewed_episode_ids": [row["episode_id"] for row in bundle["episodes"]],
            "episode_reviews": [{"episode_id": row["episode_id"], "status": "model_review_passed",
                                 "source_revision": row["source_revision"],
                                 "draft_sha256": fingerprint_draft(row["draft"]),
                                 "review_model": "test-reviewer", "issues": []}
                                for row in bundle["episodes"]],
            "review_model": "test-reviewer", "issues": []}


def manual_fixture(original, bundle):
    return {"verdict": "conversation_only_draft_acceptable",
            "source_revision": original["source_revision"],
            "draft_sha256": fingerprint_episode_bundle(bundle), "reviewer": "manual",
            "scope_verdict": "whole_session_scope_acceptable",
            "reviewed_source_message_count": len(original["messages"]),
            "episode_scope_verdict": "multiple_topics",
            "episode_partition_verdict": "exact_contiguous_partition_acceptable",
            "reviewed_episode_ids": [row["episode_id"] for row in bundle["episodes"]],
            "reviewed_at": "2026-09-27T01:00:00Z"}


class ContextEpisodePipelineTests(unittest.TestCase):
    def test_publish_creates_parent_directory_and_separate_reviewed_episode_summaries(self):
        original = source()
        bundle = bundle_fixture(original)
        review = review_fixture(bundle)
        manual = manual_fixture(original, bundle)
        row = build_session_context(THREAD_ID, "project-a", ["seed.md"], "STALE_COMBINED_SEED")

        published = promote_episode_bundle(row, original, bundle, review, manual)

        self.assertEqual(published["status"], "episode_directory_ready")
        self.assertEqual(len(published["episodes"]), 2)
        self.assertNotIn("STALE_COMBINED_SEED", "\n".join(published["summary"].values()))
        self.assertTrue(all(item["status"] == "model_reviewed" for item in published["episodes"]))
        self.assertEqual(published["manual_source_coverage"]["reviewed_source_message_count"], 4)

    def test_one_rejected_episode_blocks_the_whole_publication(self):
        original = source()
        bundle = bundle_fixture(original)
        review = review_fixture(bundle)
        review["status"] = "model_review_rejected"
        review["episode_reviews"][1]["status"] = "model_review_rejected"

        with self.assertRaisesRegex(ValueError, "scenario_episode_review_failed"):
            promote_episode_bundle(build_session_context(THREAD_ID, "p", [], "seed"), original,
                                   bundle, review, manual_fixture(original, bundle))

    def test_unreviewed_cross_chunk_claim_blocks_publication_even_if_status_says_passed(self):
        original = source()
        bundle = bundle_fixture(original)
        review = review_fixture(bundle)
        review["episode_reviews"][0]["review_coverage"] = {
            "source_chunk_count": 2, "reviewed_chunk_count": 2,
            "all_chunks_accepted": True, "unreviewed_cross_chunk_claim_count": 1,
        }

        with self.assertRaisesRegex(ValueError, "scenario_episode_review_coverage_incomplete"):
            promote_episode_bundle(build_session_context(THREAD_ID, "p", [], "seed"), original,
                                   bundle, review, manual_fixture(original, bundle))

    def test_inconsistent_cross_chunk_review_counts_block_publication(self):
        original = source()
        bundle = bundle_fixture(original)
        review = review_fixture(bundle)
        review["episode_reviews"][0]["review_coverage"] = {
            "source_chunk_count": 1, "reviewed_chunk_count": 1,
            "all_chunks_accepted": True, "cross_chunk_claim_count": 1,
            "cross_chunk_claim_reviewed_count": 0,
            "unreviewed_cross_chunk_claim_count": 0,
        }

        with self.assertRaisesRegex(ValueError, "scenario_episode_review_coverage_incomplete"):
            promote_episode_bundle(build_session_context(THREAD_ID, "p", [], "seed"), original,
                                   bundle, review, manual_fixture(original, bundle))

    def test_manual_review_must_cover_exact_episode_order_and_strict_message_count(self):
        original = source()
        bundle = bundle_fixture(original)
        review = review_fixture(bundle)
        manual = manual_fixture(original, bundle)
        manual["reviewed_episode_ids"].reverse()
        with self.assertRaisesRegex(ValueError, "scenario_episode_partition_review_unresolved"):
            promote_episode_bundle(build_session_context(THREAD_ID, "p", [], "seed"), original,
                                   bundle, review, manual)
        manual = manual_fixture(original, bundle)
        manual["reviewed_source_message_count"] = True
        with self.assertRaisesRegex(ValueError, "scenario_promotion_coverage_unresolved"):
            promote_episode_bundle(build_session_context(THREAD_ID, "p", [], "seed"), original,
                                   bundle, review_fixture(bundle), manual)

    def test_changed_parent_source_revision_blocks_publication(self):
        original = source()
        bundle = bundle_fixture(original)
        stale = copy.deepcopy(bundle)
        stale["parent_source_revision"] = "older"

        with self.assertRaisesRegex(ValueError, "scenario_episode_bundle_stale_or_invalid"):
            promote_episode_bundle(build_session_context(THREAD_ID, "p", [], "seed"), original,
                                   stale, review_fixture(bundle), manual_fixture(original, bundle))


if __name__ == "__main__":
    unittest.main()
