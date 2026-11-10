import copy
import os
import tempfile
import unittest

from ham.capture_tool_response_compaction import compact_blocked_post_tool_event


class CaptureToolResponseCompactionTest(unittest.TestCase):
    def test_compacts_a_blocked_post_tool_event_only_after_archiving_its_original_response(self):
        """Removing a legacy response before its cold archive exists would lose the only source evidence."""
        original_response = "x" * 40_000
        envelope = {
            "event_id": "event-1",
            "body_text": original_response,
            "body_preview": original_response[:4096],
            "source_payload": {"tool_response": original_response, "tool_name": "mcp__evolving_profile_controller__recall"},
            "provenance": {"hook": "PostToolUse", "body_evidence": "supplied_text"},
        }
        original = copy.deepcopy(envelope)
        with tempfile.TemporaryDirectory() as root:
            compact, manifest = compact_blocked_post_tool_event(envelope, root)

        self.assertEqual(envelope, original)
        self.assertNotIn("tool_response", compact["source_payload"])
        self.assertIn("tool_response_archive", compact["source_payload"])
        self.assertLessEqual(len(compact["body_text"]), 4096)
        self.assertEqual(manifest["original_response_sha256"], manifest["tool_response_archive"]["sha256"])


if __name__ == "__main__":
    unittest.main()
