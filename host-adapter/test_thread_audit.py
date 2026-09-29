import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import evolving_profile_controller_mcp as mcp


class ThreadAuditTest(unittest.TestCase):
    def test_audit_thread_returns_user_messages_and_tool_failures_with_coverage(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            path = root_path / "2026" / "09" / "22" / "rollout-2026-09-22T23-00-00-01a0c9c2-8952-7430-89a1-9df9cc0f3511.jsonl"
            path.parent.mkdir(parents=True)
            rows = [
                {"timestamp":"2026-09-22T15:00:00Z","type":"response_item","payload":{"thread_id":"01a0c9c2-8952-7430-89a1-9df9cc0f3511","turn_id":"turn-1","type":"message","role":"user","content":[{"type":"input_text","text":"最近五天做了哪些方案"}]}},
                {"timestamp":"2026-09-22T15:00:01Z","type":"response_item","payload":{"thread_id":"01a0c9c2-8952-7430-89a1-9df9cc0f3511","turn_id":"turn-1","type":"custom_tool_call","name":"list_threads","status":"completed"}},
                {"timestamp":"2026-09-22T15:01:00Z","type":"event_msg","payload":{"thread_id":"01a0c9c2-8952-7430-89a1-9df9cc0f3511","turn_id":"turn-2","type":"item_completed","item":{"type":"McpToolCall","server":"codex_app","tool":"read_thread","status":"failed"}}},
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            with patch.object(mcp, "THREAD_SESSION_ROOT", root_path):
                value = mcp.audit_thread_history({"thread_id":"01a0c9c2-8952-7430-89a1-9df9cc0f3511"})
            body = json.loads(value["content"][0]["text"])
            self.assertEqual(body["source"], "codex_thread_history")
            self.assertEqual(body["coverage"]["turn_count"], 2)
            self.assertEqual(body["coverage"]["failed_tool_call_count"], 1)
            self.assertEqual(body["user_messages"][0]["text"], "最近五天做了哪些方案")
            self.assertEqual(body["tool_calls"][0]["name"], "list_threads")

    def test_audit_thread_rejects_non_thread_identifier(self):
        with self.assertRaises(ValueError):
            mcp.audit_thread_history({"thread_id":"not-a-thread"})


if __name__ == "__main__":
    unittest.main()
