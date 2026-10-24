import json, os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import recall


class HostIdTest(unittest.TestCase):
    def row(self, env):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ingress.jsonl"
            old = os.environ.pop("HINDSIGHT_AGENT_NAME", None)
            if env is not None:
                os.environ["HINDSIGHT_AGENT_NAME"] = env
            try:
                ok = recall.record_prompt_ingress({"promptIngressAuditPath": str(path)}, "测试提示词", "s-1", "/work", turn_id="t-1")
            finally:
                os.environ.pop("HINDSIGHT_AGENT_NAME", None)
                if old is not None:
                    os.environ["HINDSIGHT_AGENT_NAME"] = old
            self.assertTrue(ok)
            return json.loads(path.read_text(encoding="utf-8").splitlines()[-1])

    def test_unset_env_keeps_codex(self):                      # Codex hooks never set it
        r = self.row(None)
        self.assertEqual(r["host_id"], "codex")

    def test_desktop_env_is_recorded(self):
        r = self.row("claude-desktop")
        self.assertEqual(r["host_id"], "claude-desktop")

    def test_empty_env_falls_back_to_codex(self):
        self.assertEqual(self.row("")["host_id"], "codex")

    def test_nothing_else_in_the_receipt_changed(self):
        r = self.row("claude-desktop")
        self.assertEqual(r["source"], "codex-userpromptsubmit")      # untouched on purpose
        self.assertEqual((r["event"], r["session_id"], r["turn_id"], r["cwd"], r["prompt_origin"]),
                         ("prompt_ingress", "s-1", "t-1", "/work", "user_direct"))


if __name__ == "__main__":
    unittest.main()
