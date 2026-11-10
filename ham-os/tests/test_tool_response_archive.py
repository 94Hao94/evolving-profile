import os
import tempfile
import unittest
from pathlib import Path

from ham import adapter
from ham.adapter import event_from_hook, read_archived_tool_response


class ToolResponseArchiveTest(unittest.TestCase):
    def test_large_post_tool_response_is_preserved_once_outside_capture_envelope(self):
        """Duplicating large tool output in body_text and source_payload caused permanent 413 capture bloat."""
        original = "x" * 40_000
        with tempfile.TemporaryDirectory() as root:
            previous = os.environ.get("HAM_CAPTURE_STATE_DIR")
            os.environ["HAM_CAPTURE_STATE_DIR"] = root
            try:
                payload = event_from_hook(
                    "PostToolUse",
                    {"session_id": "session-1", "cwd": "/project", "turn_id": "turn-1", "tool_response": original},
                    "tool_result",
                    "tool",
                )
            finally:
                if previous is None:
                    os.environ.pop("HAM_CAPTURE_STATE_DIR", None)
                else:
                    os.environ["HAM_CAPTURE_STATE_DIR"] = previous

            source = payload["source_payload"]
            self.assertNotIn("tool_response", source)
            self.assertIn("tool_response_archive", source)
            self.assertLessEqual(len(payload["body_text"]), 4096)
            self.assertEqual(read_archived_tool_response(source, Path(root)), original)

    def test_archive_failure_preserves_the_legacy_full_tool_response(self):
        """Cold-store failure must retain evidence even though the envelope becomes larger."""
        original = "x" * 40_000
        with tempfile.TemporaryDirectory() as root:
            previous = os.environ.get("HAM_CAPTURE_STATE_DIR")
            os.environ["HAM_CAPTURE_STATE_DIR"] = root
            original_archive = adapter._archive_tool_response
            adapter._archive_tool_response = lambda response, capture_root: (_ for _ in ()).throw(OSError("disk unavailable"))
            try:
                payload = event_from_hook(
                    "PostToolUse",
                    {"session_id": "session-2", "cwd": "/project", "turn_id": "turn-2", "tool_response": original},
                    "tool_result",
                    "tool",
                )
            finally:
                adapter._archive_tool_response = original_archive
                if previous is None:
                    os.environ.pop("HAM_CAPTURE_STATE_DIR", None)
                else:
                    os.environ["HAM_CAPTURE_STATE_DIR"] = previous

        self.assertEqual(payload["source_payload"]["tool_response"], original)
        self.assertEqual(payload["body_text"], original)


if __name__ == "__main__":
    unittest.main()
