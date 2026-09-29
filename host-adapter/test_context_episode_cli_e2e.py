import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lib.context_summary import build_session_context, write_context_index
from lib.scenario_model import (fingerprint_episode_bundle, fingerprint_episode_review,
                                request_episode_bundle, request_episode_bundle_review)
from lib.scenario_source import read_session_source


HERE = Path(__file__).resolve().parent
THREAD_ID = "01a0aad3-d9dd-7400-b1e7-a636388cab3b"


def provider_response(value):
    body = {"choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps(value, ensure_ascii=False)}}]}
    return io.BytesIO(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def fixture_provider(request, timeout):
    payload = json.loads(request.data)
    prompt = payload["messages"][0]["content"]
    envelope = json.loads(prompt.rsplit("输入：", 1)[1])
    request_type = envelope.get("request_type")
    if request_type in {"episode_boundary_classification", "episode_chunk_boundary_reconciliation"}:
        target_ids = envelope.get("target_message_ids") or [row["message_id"] for row in envelope["boundaries"]]
        messages = {row["message_id"]: row.get("text", "") for row in envelope.get("messages") or []}
        for boundary in envelope.get("boundaries") or []:
            for row in boundary.get("next_messages") or []:
                messages[row["message_id"]] = row.get("text", "")
        decisions = [{"message_id": message_id,
                      "decision": "new_episode" if "另一个任务" in messages.get(message_id, "")
                      else "same_episode"} for message_id in target_ids]
        return provider_response({"source_revision": envelope["source_revision"], "decisions": decisions})
    if "accept\"" in prompt or '"draft"' in envelope:
        return provider_response({"source_revision": envelope["source_revision"],
                                  "accept": True, "issues": []})
    users = [row for row in envelope["messages"] if row["role"] == "user"]
    assistants = [row for row in envelope["messages"] if row["role"] == "assistant"]
    user_id = users[0]["message_id"]
    return provider_response({"source_revision": envelope["source_revision"],
        "state": {"subject": {"text": users[0]["text"][:40], "message_ids": [user_id]},
                  "goal": {"text": "完成该段工作", "message_ids": [user_id]},
                  "phase": "assistant_reported", "constraints": [], "corrections": [],
                  "assistant_reports": [{"text": "助手报告已答复",
                                         "message_ids": [assistants[-1]["message_id"]]}],
                  "unresolved": []}})


class ContextEpisodeCliEndToEndTests(unittest.TestCase):
    def test_dry_run_review_and_publish_eligibility_do_not_mutate_context_index(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            sessions = root / "sessions"
            sessions.mkdir()
            transcript = sessions / f"rollout-1-{THREAD_ID}.jsonl"
            transcript_rows = [
                {"type": "response_item", "payload": {"type": "message", "role": "user",
                 "content": [{"type": "input_text", "text": "请编制项目甲方案"}]}},
                {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                 "phase": "final_answer", "content": [{"type": "output_text", "text": "项目甲方案已完成"}]}},
                {"type": "response_item", "payload": {"type": "message", "role": "user",
                 "content": [{"type": "input_text", "text": "另一个任务：比较项目乙预算"}]}},
                {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                 "phase": "final_answer", "content": [{"type": "output_text", "text": "项目乙预算已比较"}]}},
            ]
            transcript.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in transcript_rows),
                                  encoding="utf-8")
            index = root / "context-index.json"
            session = build_session_context(THREAD_ID, "project-a", [str(transcript)], "seed")
            write_context_index(index, [session], [])
            index_before = index.read_bytes()
            source = read_session_source(THREAD_ID, sessions, max_chars=500000)
            bundle = request_episode_bundle(source, base_url="https://example.invalid", api_key="fixture",
                                            model="fixture", opener=fixture_provider)
            draft_dir = root / "drafts"
            draft_dir.mkdir()
            draft_path = draft_dir / (THREAD_ID + ".json")
            draft_path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
            draft_attempt = draft_dir / ".attempts" / ("episode-" + THREAD_ID + ".json")
            draft_attempt.parent.mkdir()
            draft_attempt.write_text(json.dumps({"status": "succeeded",
                "source_revision": source["source_revision"],
                "draft_sha256": fingerprint_episode_bundle(bundle)}), encoding="utf-8")

            review_dir = root / "reviews"
            review_dry_run = subprocess.run([
                sys.executable, str(HERE / "context-episode-review-pilot.py"),
                "--session-id", THREAD_ID, "--session-root", str(sessions), "--index", str(index),
                "--draft-dir", str(draft_dir), "--output-dir", str(review_dir), "--dry-run",
            ], cwd=HERE, capture_output=True, text=True, check=False)
            self.assertEqual(review_dry_run.returncode, 0, review_dry_run.stderr)
            self.assertEqual(json.loads(review_dry_run.stdout)["items"][0]["status"], "source_ready")
            self.assertFalse(review_dir.exists())

            review = request_episode_bundle_review(source, bundle, base_url="https://example.invalid",
                api_key="fixture", model="fixture-reviewer", opener=fixture_provider)
            review_dir.mkdir()
            (review_dir / (THREAD_ID + ".json")).write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
            review_attempt = review_dir / ".attempts" / ("episode-" + THREAD_ID + ".json")
            review_attempt.parent.mkdir()
            review_attempt.write_text(json.dumps({"status": "succeeded",
                "source_revision": source["source_revision"],
                "review_sha256": fingerprint_episode_review(review)}), encoding="utf-8")
            audit = root / "manual-audit.json"
            audit.write_text(json.dumps({"audited_at": "2026-09-27T15:00:00Z",
                "manual_spot_check": {"items": [{
                    "context_id": "session:" + THREAD_ID,
                    "verdict": "conversation_only_draft_acceptable",
                    "source_revision": source["source_revision"],
                    "draft_sha256": fingerprint_episode_bundle(bundle),
                    "scope_verdict": "whole_session_scope_acceptable",
                    "reviewed_source_message_count": len(source["messages"]),
                    "episode_scope_verdict": "multiple_topics",
                    "episode_partition_verdict": "exact_contiguous_partition_acceptable",
                    "reviewed_episode_ids": [row["episode_id"] for row in bundle["episodes"]],
                    "reviewer": "test-reviewer",
                }]}}, ensure_ascii=False), encoding="utf-8")

            publish_dry_run = subprocess.run([
                sys.executable, str(HERE / "context-episode-publish-pilot.py"),
                "--session-id", THREAD_ID, "--session-root", str(sessions), "--index", str(index),
                "--draft-dir", str(draft_dir), "--review-dir", str(review_dir),
                "--audit", str(audit), "--dry-run",
            ], cwd=HERE, capture_output=True, text=True, check=False)
            self.assertEqual(publish_dry_run.returncode, 0, publish_dry_run.stderr)
            self.assertEqual(json.loads(publish_dry_run.stdout)["status"], "eligible")
            self.assertEqual(index.read_bytes(), index_before)


if __name__ == "__main__":
    unittest.main()
