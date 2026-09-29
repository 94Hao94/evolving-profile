import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.assistant_retention_shadow import record_final_answer_shadow


class AssistantRetentionShadowTest(unittest.TestCase):
    def test_records_source_anchor_and_classification_without_copying_assistant_body(self):
        """A shadow manifest must be actionable without becoming another raw transcript store."""
        messages = [
            {"role": "user", "content": "请检查归档实现"},
            {
                "role": "assistant",
                "content": "已通过归档回读验证，产物在 /tmp/result.json。",
                "source_record": {"transcript_path": "/source/rollout.jsonl", "byte_offset": 410},
            },
        ]
        with tempfile.TemporaryDirectory() as root:
            result = record_final_answer_shadow(messages, Path(root), "session-1", "/project")
            manifest = Path(result["manifest_path"]).read_text(encoding="utf-8")

        self.assertEqual(result["recorded"], 1)
        self.assertEqual(result["categories"], {"tool_verified_result": 1})
        self.assertIn('"source_record"', manifest)
        self.assertIn('"content_sha256"', manifest)
        self.assertNotIn("已通过归档回读验证", manifest)


if __name__ == "__main__":
    unittest.main()
