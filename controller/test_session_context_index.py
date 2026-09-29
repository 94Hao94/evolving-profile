import json
import os
import tempfile
import unittest

from lib.session_context_index import index_transcript, retrieve_context_bundle


class SessionContextIndexTests(unittest.TestCase):
    def test_incremental_index_recovers_old_relevant_turn_without_replaying_whole_log(self):
        with tempfile.TemporaryDirectory() as directory:
            transcript = os.path.join(directory, "task.jsonl")
            database = os.path.join(directory, "context.sqlite")
            rows = [
                {"role": "user", "content": "请测试真实 Hook 与 shadow replay 是否一致。"},
                {"role": "assistant", "content": "会核对 Hook、Controller、Bank、Packet 和 9998 回执。"},
            ]
            rows.extend({"role": "user", "content": "无关历史" + str(index)} for index in range(30))
            with open(transcript, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            receipt = index_transcript(transcript, database)
            bundle = retrieve_context_bundle(
                "你测试的真实吗", database, source_path=transcript,
                recent_limit=4, older_limit=4,
            )
            self.assertEqual(receipt["indexed_messages"], len(rows))
            self.assertTrue(bundle["older_matches"])
            self.assertIn("shadow replay", bundle["rendered_context"])
            self.assertLess(len(bundle["rendered_context"].encode("utf-8")), 16000)

    def test_context_bundle_never_leaks_a_different_codex_session(self):
        with tempfile.TemporaryDirectory() as directory:
            current = os.path.join(directory, "current.jsonl")
            foreign = os.path.join(directory, "foreign.jsonl")
            database = os.path.join(directory, "context.sqlite")
            for path, message in (
                (current, "请核对本任务的 Hook 注入是否真实。"),
                (foreign, "天津光泰科技集团的厂家品牌必须全部去掉。"),
            ):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(json.dumps({"role": "user", "content": message}, ensure_ascii=False) + "\n")
                index_transcript(path, database)
            bundle = retrieve_context_bundle(
                "按你推荐的立即执行", database, source_path=current,
                recent_limit=4, older_limit=4,
            )
            self.assertIn("Hook 注入", bundle["rendered_context"])
            self.assertNotIn("天津光泰", bundle["rendered_context"])


if __name__ == "__main__":
    unittest.main()
