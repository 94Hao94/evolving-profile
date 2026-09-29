import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.context_summary import (
    BUDGETS,
    build_project_context,
    build_session_context,
    bounded_summary,
    estimate_tokens,
    write_context_index,
    build_index_from_codex_memory,
    context_navigation,
)
from lib import context_summary
from lib.context_pipeline import apply_model_result, prepare_jobs, progress_snapshot, promote_session_draft
from lib.context_associations import associate_records, project_key
from lib import context_associations
from lib.context_retry import run_with_retry
from lib.scenario_gate import decide_scenario_summary
from lib.scenario_model import fingerprint_draft
from lib.scenario_source import read_session_source
from lib.scenario_episodes import partition_source
from lib.scenario_state_v3 import validate_state_draft
import evolving_profile_controller_mcp as controller


class ContextSummaryTest(unittest.TestCase):
    def test_uncertain_candidates_share_one_source_linked_scenario_without_body_injection(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'context.json'
            session=build_session_context('s1','p1',['r1'],'PRIVATE_SUMMARY')
            write_context_index(path,[session],[])
            rows=[{'id':'a','metadata':{'session_ids':['s1']},'relevance':{'state':'uncertain'}},
                  {'id':'b','metadata':{'session_ids':['s1']},'relevance':{'state':'literal_match'}}]
            with patch.object(controller,'CONTEXT_INDEX_PATH',path):
                result=controller.scenario_followup({'memories':rows})
        self.assertEqual(len(result['scenarios']),1)
        self.assertEqual(result['scenarios'][0]['uncertain_source_memory_ids'],['a'])
        self.assertEqual(result['scenarios'][0]['source_memory_ids'],['a','b'])
        self.assertNotIn('PRIVATE_SUMMARY',json.dumps(result))
        self.assertEqual(result['scenarios'][0]['summary_review_status'],'seeded_pending_review')

    def test_budget_is_tiered_and_unicode_safe(self):
        text = "项目摘要：" + "这是一个复杂的上下文。" * 600
        for context_type, expected in (("session", BUDGETS["session"]), ("project", BUDGETS["project"])):
            for tier, limits in expected.items():
                value, receipt = bounded_summary(text, context_type, tier)
                self.assertLessEqual(len(value), limits["max_chars"])
                self.assertLessEqual(estimate_tokens(value), limits["max_tokens"])
                self.assertEqual(value.encode("utf-8").decode("utf-8"), value)
                self.assertEqual(receipt["tier"], tier)

    def test_session_context_keeps_provenance_and_does_not_claim_bank_fact(self):
        context = build_session_context(
            session_id="sess-1",
            project_key="project-a",
            source_ids=["rollout-1", "rollout-1", "rollout-2"],
            seed_text="用户讨论了摘要预算，并决定使用 GPT-6 Luna 做轻推理批处理。",
            updated_at="2026-09-24T00:00:00Z",
        )
        self.assertEqual(context["context_type"], "session")
        self.assertEqual(context["session_id"], "sess-1")
        self.assertEqual(context["project_key"], "project-a")
        self.assertEqual(context["source_ids"], ["rollout-1", "rollout-2"])
        self.assertEqual(context["status"], "seeded_pending_review")
        self.assertIn("摘要预算", context["summary"]["standard"])
        self.assertNotIn("bank_fact", context)

    def test_project_context_aggregates_sessions_without_cross_project_leakage(self):
        sessions = [
            build_session_context("s1", "project-a", ["r1"], "项目A先做导入。", "2026-09-20T00:00:00Z"),
            build_session_context("s2", "project-a", ["r2"], "项目A再做回归测试。", "2026-09-21T00:00:00Z"),
            build_session_context("s3", "project-b", ["r3"], "项目B不应进入项目A。", "2026-09-22T00:00:00Z"),
        ]
        project = build_project_context("project-a", sessions, updated_at="2026-09-24T00:00:00Z")
        self.assertEqual(project["context_type"], "project")
        self.assertEqual(project["session_ids"], ["s1", "s2"])
        self.assertEqual(project["source_ids"], ["r1", "r2"])
        self.assertEqual(project["identity_status"], "unverified_workspace_bucket")
        self.assertIn("回归测试", project["summary"]["standard"])
        self.assertNotIn("项目B", project["summary"]["standard"])

    def test_project_context_does_not_mislabel_nonempty_session_after_empty_one(self):
        sessions = [
            build_session_context("s1", "p1", ["r1"], ""),
            build_session_context("s2", "p1", ["r2"], "第二会话的内容"),
        ]
        project = build_project_context("p1", sessions)
        self.assertIn("[s2] 第二会话的内容", project["summary"]["full"])
        self.assertNotIn("[s1] 第二会话的内容", project["summary"]["full"])

    def test_deterministic_projection_keeps_inherited_truncation_and_unreviewed_status(self):
        row = build_session_context("s1", "p1", ["r1"], "来源已截断…")
        row["summary_budget"]["full"]["truncated"] = True
        self.assertTrue(hasattr(context_summary, "reproject_context_row"))
        projected = context_summary.reproject_context_row(row)
        self.assertEqual(projected["status"], "deterministic_projection_unreviewed")
        self.assertTrue(projected["summary_budget"]["full"]["truncated"])
        self.assertEqual(projected["processing_method"], "deterministic_source_projection")

    def test_compact_truncation_does_not_mark_complete_full_summary_as_truncated(self):
        row = build_session_context("s1", "p1", ["r1"], "摘要内容" * 200)
        self.assertTrue(row["summary_budget"]["compact"]["truncated"])
        self.assertFalse(row["summary_budget"]["full"]["truncated"])
        projected = context_summary.reproject_context_row(row)
        self.assertFalse(projected["summary_budget"]["full"]["truncated"])

    def test_direct_worker_can_run_in_isolation_without_claiming_review(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            row = build_session_context("s1", "p1", ["r1"], "来源摘要")
            index = folder / "index.json"
            write_context_index(index, [row], [])
            queue = folder / "queue.json"
            queue.write_text(json.dumps({"jobs": [{"context_id": "session:s1", "status": "queued"}]}))
            progress = folder / "progress.json"
            script = Path(__file__).with_name("context-direct-worker.py")
            result = subprocess.run([sys.executable, str(script), "--index", str(index),
                                     "--queue", str(queue), "--progress", str(progress)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(index.read_text())["sessions"][0]["status"],
                             "deterministic_projection_unreviewed")
            receipt = json.loads(progress.read_text())
            self.assertEqual(receipt["status"], "review_pending")
            self.assertEqual(receipt["review_pending"], 1)

    def test_recall_exposes_only_linked_scenario_navigation_not_summary_text(self):
        from unittest.mock import patch
        from lib.context_associations import project_key
        with tempfile.TemporaryDirectory() as root:
            key = project_key("/workspace/demo")
            session = build_session_context("s1", key, ["r1"], "PRIVATE_SCENARIO_MARKER")
            project = build_project_context(key, [session])
            path = Path(root) / "context.json"
            write_context_index(path, [session], [project])
            candidate = {"id": "00000000-0000-0000-0000-000000000001", "metadata": {"session_ids": ["s1"], "project": "/workspace/demo"}, "text": "备份策略"}
            result = {"query": "备份为什么这么选", "memories": [candidate], "next_offset": None}
            with patch.object(controller, "CONTEXT_INDEX_PATH", path), patch.object(controller, "search", return_value=result), patch.object(controller, "guidance_value", return_value={}):
                payload = json.loads(controller.evidence_recall({"query": result["query"]})["content"][0]["text"])
        followup = payload["scenario_followup"]
        self.assertEqual(followup["decision"], "agent_decides")
        self.assertEqual({item["scenario_id"] for item in followup["scenarios"]}, {"session:s1"})
        self.assertEqual(followup["excluded_unverified_workspace_count"], 1)
        self.assertNotIn("PRIVATE_SCENARIO_MARKER", json.dumps(followup))

    def test_recall_can_offer_project_only_after_identity_review(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            session = build_session_context("s1", "p1", ["r1"], "会话")
            project = build_project_context("p1", [session])
            project["identity_status"] = "verified_project"
            path = Path(root) / "context.json"
            write_context_index(path, [session], [project])
            candidate = {"id": "m1", "metadata": {"project_key": "p1", "session_ids": ["s1"]}}
            with patch.object(controller, "CONTEXT_INDEX_PATH", path):
                followup = controller.scenario_followup({"memories": [candidate]})
        self.assertEqual({item["scenario_id"] for item in followup["scenarios"]}, {"session:s1", "project:p1"})

    def test_scenario_locator_has_navigation_title_not_summary_and_marks_batch_ambiguity(self):
        with tempfile.TemporaryDirectory() as root:
            one = build_session_context("s1", "p1", [], "# 30万元课程项目\nPRIVATE_SUMMARY_BODY")
            two = build_session_context("s2", "p1", [], "# 50万元实训平台\nOTHER_PRIVATE_BODY")
            path = Path(root) / "index.json"
            write_context_index(path, [one, two], [])
            candidate = {"id": "m1", "metadata": {"session_ids": "s1,s2"}}
            with patch.object(controller, "CONTEXT_INDEX_PATH", path):
                result = controller.scenario_followup({"memories": [candidate]})
        self.assertEqual([s['navigation_title'] for s in result['scenarios']],
                         ['30万元课程项目', '50万元实训平台'])
        self.assertNotIn('PRIVATE_SUMMARY_BODY', json.dumps(result))
        self.assertTrue(all(s['source_linkage_ambiguous'] for s in result['scenarios']))
        self.assertEqual(result['next_action'], 'check_scenario_if_scope_or_revision_unresolved')

    def test_write_context_index_is_atomic_and_readable(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "context.json"
            rows = [build_session_context("s1", "p1", ["r1"], "摘要", "2026-09-24T00:00:00Z")]
            receipt = write_context_index(path, rows, [build_project_context("p1", rows, "2026-09-24T00:00:00Z")])
            self.assertTrue(receipt["ok"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "evolving-profile.context-index.v1")
            self.assertEqual(len(payload["sessions"]), 1)
            self.assertEqual(len(payload["projects"]), 1)

    def test_read_context_summary_returns_selected_tier_and_provenance(self):
        with tempfile.TemporaryDirectory() as root:
            rows = [build_session_context("s1", "p1", ["r1"], "会话上下文", "2026-09-24T00:00:00Z")]
            path = Path(root) / "context.json"
            write_context_index(path, rows, [build_project_context("p1", rows, "2026-09-24T00:00:00Z")])
            old = controller.CONTEXT_INDEX_PATH
            controller.CONTEXT_INDEX_PATH = path
            try:
                result = controller.read_context_summary({"context_type": "session", "session_id": "s1", "tier": "standard"})
            finally:
                controller.CONTEXT_INDEX_PATH = old
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["items"][0]["summary"], "会话上下文")
        self.assertEqual(payload["items"][0]["source_ids"], ["r1"])
        self.assertEqual(payload["items"][0]["evidence_role"], "context_navigation_only")

    def test_episode_directory_hides_bodies_and_explicit_read_returns_one_current_episode(self):
        session_id = "01a0aad3-d9dd-7400-b1e7-a636388cab3b"
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            sessions = root / "sessions"
            sessions.mkdir()
            transcript = sessions / f"rollout-1-{session_id}.jsonl"

            def append_turn(role, text):
                phase = "final_answer" if role == "assistant" else "user"
                block = "output_text" if role == "assistant" else "input_text"
                row = {"type": "response_item", "payload": {"type": "message", "role": role,
                       "phase": phase, "content": [{"type": block, "text": text}]}}
                with transcript.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")

            append_turn("user", "请编制项目甲方案")
            append_turn("assistant", "项目甲方案已完成")
            append_turn("user", "另一个任务：比较项目乙预算")
            append_turn("assistant", "项目乙预算已比较")
            original = read_session_source(session_id, sessions, max_chars=500000)
            partitions = partition_source(original, [original["messages"][2]["evidence_id"]])
            episode_rows = []
            for position, part in enumerate(partitions, 1):
                episode_rows.append({key: part[key] for key in (
                    "episode_id", "parent_session_id", "parent_source_revision", "source_revision",
                    "start_message_id", "start_user_message_id", "end_message_id", "message_ids",
                    "source_message_count", "source_file_ids", "source_offsets")})
                episode_rows[-1].update({"title": f"项目{position}任务",
                    "title_authority": "navigation_label_not_verified_fact",
                    "summary": {"compact": f"compact-body-{position}",
                                "standard": f"standard-body-{position}",
                                "full": f"full-body-{position}"},
                    "status": "model_reviewed", "evidence_role": "context_navigation_only"})
            row = build_session_context(session_id, "project-a", ["seed.md"], "旧的合并摘要")
            row.update(status="episode_directory_ready", source_revision=original["source_revision"],
                       raw_source_files=original["source_files"], source_message_count=len(original["messages"]),
                       episodes=episode_rows)
            index = root / "context-index.json"
            write_context_index(index, [row], [])
            with patch.object(controller, "CONTEXT_INDEX_PATH", index), \
                    patch.object(controller, "THREAD_SESSION_ROOT", sessions):
                directory = json.loads(controller.read_context_summary({
                    "context_type": "session", "session_id": session_id})["content"][0]["text"])
                selected = json.loads(controller.read_context_summary({
                    "context_type": "session", "session_id": session_id,
                    "episode_id": episode_rows[0]["episode_id"], "tier": "standard"
                })["content"][0]["text"])

        parent = directory["items"][0]
        self.assertEqual(len(parent["episodes"]), 2)
        self.assertNotIn("summary", parent["episodes"][0])
        self.assertNotIn("compact-body-1", json.dumps(directory, ensure_ascii=False))
        self.assertEqual(selected["items"][0]["episode_id"], episode_rows[0]["episode_id"])
        self.assertEqual(selected["items"][0]["summary"], "standard-body-1")
        self.assertNotIn("standard-body-2", json.dumps(selected, ensure_ascii=False))

    def test_appending_source_withholds_the_last_episode_body_until_reindexed(self):
        session_id = "01a0aad3-d9dd-7400-b1e7-a636388cab3b"
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            sessions = root / "sessions"
            sessions.mkdir()
            transcript = sessions / f"rollout-1-{session_id}.jsonl"
            for role, text in (("user", "项目甲方案"), ("assistant", "已完成"),
                               ("user", "项目乙预算"), ("assistant", "已比较")):
                block = "output_text" if role == "assistant" else "input_text"
                row = {"type": "response_item", "payload": {"type": "message", "role": role,
                       "phase": "final_answer" if role == "assistant" else "user",
                       "content": [{"type": block, "text": text}]}}
                with transcript.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            original = read_session_source(session_id, sessions, max_chars=500000)
            partitions = partition_source(original, [original["messages"][2]["evidence_id"]])
            episodes = []
            for position, part in enumerate(partitions, 1):
                episodes.append({key: part[key] for key in (
                    "episode_id", "parent_session_id", "parent_source_revision", "source_revision",
                    "start_message_id", "start_user_message_id", "end_message_id", "message_ids",
                    "source_message_count", "source_file_ids", "source_offsets")})
                episodes[-1].update({"title": f"任务{position}", "summary": {
                    "compact": f"C{position}", "standard": f"S{position}", "full": f"F{position}"},
                    "status": "model_reviewed"})
            row = build_session_context(session_id, "p", [], "directory")
            row.update(status="episode_directory_ready", source_revision=original["source_revision"],
                       episodes=episodes)
            index = root / "context-index.json"
            write_context_index(index, [row], [])
            row_before_append = len(transcript.read_bytes())
            block = {"type": "response_item", "payload": {"type": "message", "role": "user",
                     "phase": "user", "content": [{"type": "input_text", "text": "项目乙再补充一点"}]}}
            with transcript.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(block, ensure_ascii=False) + "\n")
            with patch.object(controller, "CONTEXT_INDEX_PATH", index), \
                    patch.object(controller, "THREAD_SESSION_ROOT", sessions):
                stale = json.loads(controller.read_context_summary({
                    "context_type": "session", "session_id": session_id,
                    "episode_id": episodes[-1]["episode_id"], "tier": "compact"
                })["content"][0]["text"])
                stable = json.loads(controller.read_context_summary({
                    "context_type": "session", "session_id": session_id,
                    "episode_id": episodes[0]["episode_id"], "tier": "compact"
                })["content"][0]["text"])

        self.assertGreater(row_before_append, 0)
        self.assertEqual(stale["status"], "stale_source_changed")
        self.assertNotIn("summary", stale["items"][0])
        self.assertEqual(stable["status"], "span_current_parent_revision_changed")
        self.assertTrue(stable["items"][0]["parent_source_revision_changed"])
        self.assertEqual(stable["items"][0]["summary"], "C1")

    def test_reviewed_scenario_reader_exposes_raw_source_revision_and_review_scope(self):
        with tempfile.TemporaryDirectory() as root:
            row = build_session_context("s1", "p1", ["seed.md"], "摘要")
            row.update(status="model_reviewed", source_revision="revision-1",
                       raw_source_files=["/rollouts/session.jsonl"],
                       review_scope="conversation_only_not_external_fact_verification",
                       manual_source_coverage={"scope_verdict": "whole_session_scope_acceptable",
                                               "reviewed_source_message_count": 160,
                                               "episode_scope_verdict": "single_coherent_task"})
            path = Path(root) / "context.json"
            write_context_index(path, [row], [])
            with patch.object(controller, "CONTEXT_INDEX_PATH", path):
                result = controller.read_context_summary({"context_type": "session", "session_id": "s1"})
        item = json.loads(result["content"][0]["text"])["items"][0]
        self.assertEqual(item["source_revision"], "revision-1")
        self.assertEqual(item["raw_source_files"], ["/rollouts/session.jsonl"])
        self.assertEqual(item["review_scope"], "conversation_only_not_external_fact_verification")
        self.assertEqual(item["manual_source_coverage"]["episode_scope_verdict"], "single_coherent_task")

    def test_manual_episode_scope_survives_promotion_index_and_scenario_read(self):
        session_id = "01a0aad3-d9dd-7400-b1e7-a636388cab3b"
        messages = [
            {"evidence_id": "id1", "role": "user", "text": "天津大学墙体巡检方案", "turn_id": "t1", "at": "2026-09-27T01:00:00Z"},
            {"evidence_id": "id2", "role": "assistant", "text": "旧稿已完成", "turn_id": "t2", "at": "2026-09-27T02:00:00Z"},
            {"evidence_id": "id3", "role": "user", "text": "改成背负式喷洒", "turn_id": "t3", "at": "2026-09-27T03:00:00Z"},
            {"evidence_id": "id4", "role": "assistant", "text": "新版已形成", "turn_id": "t4", "at": "2026-09-27T04:00:00Z"},
        ]
        source = {"thread_id": session_id, "source": "codex_thread_history",
                  "source_files": ["rollout.jsonl"], "source_revision": "revision-1",
                  "status": "complete", "messages": messages}
        claim = lambda text, message_id: {"text": text, "message_ids": [message_id]}
        state = {"subject": claim("天津大学墙体巡检方案", "id1"),
                 "goal": claim("编制巡检方案", "id1"), "phase": "assistant_reported",
                 "constraints": [], "corrections": [claim("改成背负式喷洒", "id3")],
                 "assistant_reports": [claim("新版已形成", "id4")], "unresolved": []}
        draft = validate_state_draft(source, state, model="test-model")
        draft["source_chunk_char_limit"] = 20
        draft["selection_coverage"] = {"source_revision": "revision-1", "source_message_count": 4,
            "source_chunk_count": 2, "candidate_state_count": 2, "chunk_char_limit": 20,
            "semantic_completeness_proven": False}
        digest = fingerprint_draft(draft)
        row = build_session_context(session_id, "workspace", ["seed.md"], "旧导航")
        review = {"status": "model_review_passed", "source_revision": "revision-1", "issues": [],
                  "draft_sha256": digest, "review_model": "test-model"}
        review["review_coverage"] = {"source_chunk_count": 2, "source_chunk_char_limit": 20,
            "reviewed_chunk_count": 2, "all_chunks_accepted": True,
            "cross_chunk_claim_count": 0, "cross_chunk_claim_reviewed_count": 0,
            "unreviewed_cross_chunk_claim_count": 0}
        manual = {"verdict": "conversation_only_draft_acceptable", "source_revision": "revision-1",
                  "draft_sha256": digest, "reviewer": "manual",
                  "scope_verdict": "whole_session_scope_acceptable",
                  "reviewed_source_message_count": 4,
                  "episode_scope_verdict": "single_coherent_task"}
        published = promote_session_draft(row, source, draft, review, manual)

        with tempfile.TemporaryDirectory() as root:
            index_path = Path(root) / "context.json"
            write_context_index(index_path, [published], [])
            with patch.object(controller, "CONTEXT_INDEX_PATH", index_path):
                result = controller.read_context_summary({"context_type": "session", "session_id": session_id})

        item = json.loads(result["content"][0]["text"])["items"][0]
        self.assertEqual(item["manual_source_coverage"], {
            "scope_verdict": "whole_session_scope_acceptable",
            "reviewed_source_message_count": 4,
            "episode_scope_verdict": "single_coherent_task",
        })

    def test_scenario_reader_paginates_and_labels_unreviewed_projection(self):
        with tempfile.TemporaryDirectory() as root:
            rows = [build_session_context(f"s{i}", "p1", [f"/rollouts/{i}.md"], f"摘要{i}") for i in range(25)]
            rows = [context_summary.reproject_context_row(row) for row in rows]
            path = Path(root) / "context.json"
            write_context_index(path, rows, [])
            old = controller.CONTEXT_INDEX_PATH
            controller.CONTEXT_INDEX_PATH = path
            try:
                result = controller.read_context_summary({"context_type": "session", "project_key": "p1",
                                                          "tier": "compact", "offset": 10, "limit": 10})
            finally:
                controller.CONTEXT_INDEX_PATH = old
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["status"], "available_unreviewed")
        self.assertEqual(payload["total"], 25)
        self.assertEqual(payload["next_offset"], 20)
        self.assertEqual(len(payload["items"]), 10)
        self.assertEqual(payload["items"][0]["source_locator_type"], "codex_rollout_summary_path")

    def test_project_reader_discloses_workspace_bucket_is_not_verified_project(self):
        with tempfile.TemporaryDirectory() as root:
            session = build_session_context("s1", "p1", ["r1"], "会话")
            path = Path(root) / "context.json"
            write_context_index(path, [session], [build_project_context("p1", [session])])
            with patch.object(controller, "CONTEXT_INDEX_PATH", path):
                result = controller.read_context_summary({"context_type": "project", "project_key": "p1"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["items"][0]["identity_status"], "unverified_workspace_bucket")

    def test_native_codex_rollout_summaries_are_imported_as_pending_seeds(self):
        with tempfile.TemporaryDirectory() as root:
            summary_dir = Path(root) / "rollout_summaries"
            summary_dir.mkdir()
            (summary_dir / "example.md").write_text(
                "thread_id: thread-1\nupdated_at: 2026-09-24T00:00:00Z\n"
                "rollout_path: /tmp/rollout.jsonl\ncwd: /workspace/demo\n\n"
                "# 摘要\n这是原生 Codex 的情境种子。\n",
                encoding="utf-8",
            )
            sessions, projects = build_index_from_codex_memory(root)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["status"], "seeded_pending_review")
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["session_ids"], ["thread-1"])

    def test_context_navigation_is_explicitly_non_factual_and_scope_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            rows = [build_session_context("s1", "/workspace/demo", ["r1"], "情境摘要", "2026-09-24T00:00:00Z")]
            path = Path(root) / "context.json"
            write_context_index(path, rows, [build_project_context("/workspace/demo", rows, "2026-09-24T00:00:00Z")])
            # build_session_context expects project_key; use the actual hash to
            # keep this assertion aligned with the hook's project identity.
            import hashlib
            project_key = hashlib.sha256(b"/workspace/demo").hexdigest()[:16]
            rows = [build_session_context("s1", project_key, ["r1"], "情境摘要", "2026-09-24T00:00:00Z")]
            write_context_index(path, rows, [build_project_context(project_key, rows, "2026-09-24T00:00:00Z")])
            block = context_navigation("s1", "/workspace/demo", path)
        self.assertIn("navigation_only_not_bank_fact", block)
        self.assertIn("情境摘要", block)
        self.assertIn("session:s1", block)

    def test_pipeline_assigns_luna_batch_and_sol_only_for_review(self):
        row = build_session_context("s1", "p1", ["r1"], "短摘要", "2026-09-24T00:00:00Z")
        queue = prepare_jobs({"sessions": [row], "projects": []})
        self.assertEqual(queue["jobs"][0]["primary_model"], "gpt-6-luna-light-reasoning")
        self.assertFalse(queue["jobs"][0]["review_required"])
        published = apply_model_result(row, {"context_id": row["context_id"], "source_ids": ["r1"],
            "summaries": {"compact": "短摘要", "standard": "标准摘要", "full": "完整摘要"},
            "status": "model_generated", "summary_model": "gpt-6-luna-light-reasoning"})
        self.assertEqual(published["status"], "model_generated")
        with self.assertRaises(ValueError):
            apply_model_result(row, {"context_id": row["context_id"], "source_ids": [], "summaries": {}, "status": "model_generated"})

    def test_association_migration_never_rewrites_record_and_marks_unknown(self):
        sessions = [build_session_context("s1", project_key("/p/a"), ["r1"], "摘要", "2026-09-24T00:00:00Z")]
        projects = [build_project_context(project_key("/p/a"), sessions, "2026-09-24T00:00:00Z")]
        result = associate_records([
            {"id": "m1", "type": "experience", "metadata": {"session_ids": "s1"}},
            {"id": "m2", "type": "world", "metadata": {}},
        ], {"sessions": sessions, "projects": projects})
        self.assertEqual(result["links"][0]["record_id"], "m1")
        self.assertEqual(result["links"][0]["session_ids"], ["s1"])
        self.assertEqual(result["unresolved"][0]["record_id"], "m2")
        self.assertEqual(result["policy"], "association_only_no_fact_rewrite")

    def test_association_snapshot_writes_valid_sidecar_atomically(self):
        self.assertTrue(hasattr(context_associations, "write_association_snapshot"))
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "links.json"
            path.write_text('{"old":true}')
            receipt = context_associations.write_association_snapshot(path, {"scanned_records": 2, "links": [{"record_id": "m1"}]})
            self.assertEqual(receipt["linked_records"], 1)
            self.assertEqual(json.loads(path.read_text())["scanned_records"], 2)
            self.assertEqual(list(path.parent.glob("links.json.*")), [])

    def test_model_job_retries_transient_failures_and_never_claims_failed_success(self):
        calls = []
        def worker(attempt):
            calls.append(attempt)
            if attempt < 3:
                error = TimeoutError("provider timeout")
                error.retryable = True
                raise error
            return {"status": "model_generated"}
        receipt = run_with_retry(worker, max_attempts=5, base_delay=0, sleep=lambda _: None)
        self.assertEqual(receipt["status"], "succeeded")
        self.assertEqual(calls, [1, 2, 3])

        failed = run_with_retry(lambda _: (_ for _ in ()).throw(ValueError("bad schema")), max_attempts=5, sleep=lambda _: None)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["attempt"], 1)

    def test_scenario_gate_requires_explicit_gap_and_never_infers_it_from_words(self):
        candidates = [
            {"id": "m1", "project_key": "p1", "session_ids": ["s1"]},
            {"id": "m1", "project_key": "p1", "session_ids": ["s1"]},
            {"id": "m2", "project_key": "p1", "session_ids": ["s2"]},
        ]
        undecided = decide_scenario_summary("为什么后来改了方案，比较新旧决定", candidates)
        self.assertEqual(undecided["decision"], "agent_decides")
        self.assertEqual(undecided["deduplicated_count"], 2)
        compact = decide_scenario_summary("当前问题", candidates, unresolved_slots=["旧决定的背景"])
        self.assertEqual(compact["decision"], "compact")
        self.assertEqual(compact["recommended_route"], "scenario_standard")
        none = decide_scenario_summary("当时为什么", candidates, current_context_sufficient=True,
                                       unresolved_slots=["旧决定的背景"])
        self.assertEqual(none["decision"], "none")
        self.assertEqual(none["recommended_route"], "none")

        raw = decide_scenario_summary("请给出当时项目会议的原话和完整对话", candidates,
                                      unresolved_slots=["原始措辞"])
        self.assertEqual(raw["recommended_route"], "audit_session")

        fact = decide_scenario_summary("核对这个项目的预算金额和最终版本", candidates,
                                       unresolved_slots=["金额", "版本"])
        self.assertEqual(fact["recommended_route"], "read_source")

    def test_scenario_gate_recognizes_bank_project_path_and_reports_missing_index_link(self):
        with_project = decide_scenario_summary("项目", [{"id": "m1", "metadata": {"project": "/p/a"}}],
                                               unresolved_slots=["背景"])
        self.assertEqual(with_project["project_count"], 1)
        missing = decide_scenario_summary("项目", [{"id": "m2", "metadata": {}}],
                                          unresolved_slots=["背景"])
        self.assertEqual(missing["decision"], "unavailable_no_scope_link")

    def test_progress_snapshot_distinguishes_queued_and_execution_states(self):
        row = build_session_context("s1", "p1", ["r1"], "摘要", "2026-09-24T00:00:00Z")
        queue = prepare_jobs({"sessions": [row], "projects": []})
        self.assertEqual(progress_snapshot(queue)["queued"], 1)
        queue["jobs"][0]["status"] = "succeeded"
        snapshot = progress_snapshot(queue)
        self.assertEqual(snapshot["succeeded"], 1)
        self.assertEqual(snapshot["queued"], 0)


if __name__ == "__main__":
    unittest.main()
