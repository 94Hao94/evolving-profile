import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lib.context_summary import build_session_context, write_context_index


HERE = Path(__file__).resolve().parent
THREAD_ID = "01a0aad3-d9dd-7400-b1e7-a636388cab3b"


class EpisodeModelCliTests(unittest.TestCase):
    def test_dry_run_reads_an_isolated_transcript_without_creating_attempt_or_draft(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            sessions = root / "sessions"
            sessions.mkdir()
            transcript = sessions / f"rollout-1-{THREAD_ID}.jsonl"
            rows = [
                {"type": "response_item", "payload": {"type": "message", "role": "user",
                 "content": [{"type": "input_text", "text": "请处理项目甲"}]}},
                {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                 "phase": "final_answer", "content": [{"type": "output_text", "text": "项目甲已处理"}]}},
            ]
            transcript.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                                  encoding="utf-8")
            index = root / "context-index.json"
            session = build_session_context(THREAD_ID, "project-a", [str(transcript)], "seed")
            write_context_index(index, [session], [])
            output = root / "episode-drafts"

            result = subprocess.run([
                sys.executable, str(HERE / "context-episode-model-pilot.py"),
                "--session-id", THREAD_ID, "--session-root", str(sessions), "--index", str(index),
                "--output-dir", str(output), "--dry-run",
            ], cwd=HERE, capture_output=True, text=True, check=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["items"][0]["status"], "source_ready")
            self.assertEqual(receipt["items"][0]["source_messages"], 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
