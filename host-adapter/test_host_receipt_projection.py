import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ham-os"))

from ham.adapter import event_from_hook
from host_receipt_projection import TOOLS, resolve_tool_response


class HostReceiptProjectionTest(unittest.TestCase):
    def test_recognizes_current_and_legacy_controller_tool_names(self):
        self.assertIn("mcp__hindsight_controller__recall", TOOLS)
        self.assertIn("mcp__hindsight_controller__research", TOOLS)
        self.assertIn("mcp__evolving_profile_controller__recall", TOOLS)
        self.assertIn("mcp__evolving_profile_controller__get_preference", TOOLS)

    def test_resolves_large_archived_tool_response(self):
        """A compact capture envelope must not make the audit projection silently lose an observed MCP response."""
        response = {"content": [{"type": "text", "text": "x" * 40_000}]}
        with tempfile.TemporaryDirectory() as root:
            previous = os.environ.get("HAM_CAPTURE_STATE_DIR")
            os.environ["HAM_CAPTURE_STATE_DIR"] = root
            try:
                envelope = event_from_hook(
                    "PostToolUse",
                    {"session_id": "session", "cwd": "/project", "turn_id": "turn", "tool_response": response},
                    "tool_result",
                    "tool",
                )
            finally:
                if previous is None:
                    os.environ.pop("HAM_CAPTURE_STATE_DIR", None)
                else:
                    os.environ["HAM_CAPTURE_STATE_DIR"] = previous

            resolved = resolve_tool_response(envelope["source_payload"], Path(root) / "capture.sqlite3")

        self.assertEqual(resolved, response)


if __name__ == "__main__":
    unittest.main()
