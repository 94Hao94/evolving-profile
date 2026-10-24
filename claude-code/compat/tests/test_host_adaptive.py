import json, os, subprocess, sys, tempfile, unittest, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import hook_bridge_desktop as hb
import desktop_rollout as dr


class DetectHostTest(unittest.TestCase):
    def test_desktop_markers(self):
        self.assertEqual(hb.detect_host({"CLAUDE_CODE_IS_COWORK": "1"}), "claude-desktop")
        self.assertEqual(hb.detect_host({"CLAUDE_CODE_ENTRYPOINT": "local-agent"}), "claude-desktop")
        self.assertEqual(hb.detect_host({"CLAUDE_CODE_ENTRYPOINT": "claude-desktop"}), "claude-desktop")
        self.assertEqual(hb.detect_host({"CLAUDE_CODE_ENTRYPOINT": "local-agent", "CLAUDE_CODE_IS_COWORK": "1"}), "claude-desktop")

    def test_cli(self):
        self.assertEqual(hb.detect_host({"CLAUDE_CODE_ENTRYPOINT": "cli"}), "claude-cli")
        self.assertEqual(hb.detect_host({"CLAUDE_CODE_ENTRYPOINT": " CLI "}), "claude-cli")
        self.assertEqual(hb.detect_host({"CLAUDE_CODE_ENTRYPOINT": "cli", "CLAUDE_CODE_IS_COWORK": "0"}), "claude-cli")

    def test_unknown_or_missing_falls_back_to_generic_and_never_raises(self):
        for env in ({}, {"CLAUDE_CODE_ENTRYPOINT": "sdk-ts"}, {"CLAUDE_CODE_ENTRYPOINT": "ide"}, {"CLAUDE_CODE_ENTRYPOINT": "something-new"}):
            self.assertEqual(hb.detect_host(env), "claude-code")

    def test_explicit_override_wins_but_must_be_safe(self):
        self.assertEqual(hb.detect_host({"EP_HOST": "codex-cli", "CLAUDE_CODE_IS_COWORK": "1"}), "codex-cli")
        self.assertEqual(hb.detect_host({"EP_HOST": "../../etc", "CLAUDE_CODE_ENTRYPOINT": "cli"}), "claude-cli")   # unsafe value ignored
        self.assertEqual(len(hb.detect_host({"EP_HOST": "a" * 100})), 40)


class TranscriptTest(unittest.TestCase):
    """Regression for the Bank contamination: Read-tool output must never become 'user' speech (any host)."""
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.d = Path(os.path.realpath(self.t.name)); hb.TRANSCRIPTS = self.d / "out"

    def tearDown(self):
        self.t.cleanup()

    def test_tool_result_file_dump_is_dropped_everywhere(self):
        dump = "\n".join(f"{i}\tprint({i})" for i in range(1, 60))
        rows = [
            {"type": "user", "message": {"role": "user", "content": "请看一下这个脚本"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "我来读文件。"}, {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/x.py"}}]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": dump}]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t2", "content": [{"type": "text", "text": dump}]}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "脚本做了打印。"}]}},
        ]
        src = self.d / "t.jsonl"; src.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
        path, n, state = hb.normalize_transcript(str(src), "s1")
        got = [json.loads(l) for l in open(path, encoding="utf-8")]
        self.assertEqual([(g["role"]) for g in got], ["user", "assistant", "assistant"])
        self.assertEqual(got[0]["content"], "请看一下这个脚本")
        self.assertFalse(any("print(" in g["content"] for g in got))

    def test_old_bridge_behaviour_is_what_the_regression_guards_against(self):
        old = (ROOT / "hook_bridge.py")
        if "runpy" in old.read_text(encoding="utf-8"):
            self.skipTest("hook_bridge.py already replaced by the shim")
        self.fail("old bridge still active: tool_result would be stored as user speech")


class RolloutHostTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.home = Path(os.path.realpath(self.t.name))
        dr.BASE = self.home / "cc"; dr.ROOT = dr.BASE / "rollouts"; dr.PENDING = dr.BASE / "rollouts-pending"; dr.OFF = dr.BASE / "off"
        dr.BASE.mkdir(parents=True); self.sid = str(uuid.uuid4()); self.tp = self.home / "t.jsonl"; self.n = 0; self.turn()

    def tearDown(self):
        self.t.cleanup()

    def turn(self):
        self.n += 1
        with open(self.tp, "a", encoding="utf-8") as f:
            f.write(json.dumps({"role": "user", "content": f"问{self.n}", "timestamp": f"2026-10-24T09:{self.n:02d}:00Z"}, ensure_ascii=False) + "\n")
            f.write(json.dumps({"role": "assistant", "content": f"答{self.n}", "timestamp": f"2026-10-24T09:{self.n:02d}:05Z"}, ensure_ascii=False) + "\n")

    def header(self):
        return json.loads(next(dr.ROOT.rglob("rollout-*.jsonl")).read_text(encoding="utf-8").splitlines()[0])["payload"]

    def test_default_is_unchanged_desktop_tag(self):
        dr.write_rollout(self.sid, str(self.tp), "/p")
        self.assertEqual((self.header()["originator"], self.header()["source"]), ("claude-desktop", "claude-desktop"))

    def test_cli_host_is_tagged(self):
        dr.write_rollout(self.sid, str(self.tp), "/p", host="claude-cli")
        self.assertEqual((self.header()["originator"], self.header()["source"]), ("claude-cli", "claude-cli"))

    def test_deferred_update_keeps_the_host_through_the_marker(self):
        dr.write_rollout(self.sid, str(self.tp), "/p", host="claude-cli"); self.turn()
        self.assertEqual(dr.write_rollout(self.sid, str(self.tp), "/p", host="claude-cli")["rollout"], "deferred")
        marker = json.loads(next(dr.PENDING.glob("*.json")).read_text()); self.assertEqual(marker["host"], "claude-cli")
        p = next(dr.ROOT.rglob("rollout-*.jsonl")); os.utime(p, (1, 1))
        self.assertEqual(dr.flush_pending(), 1); self.assertEqual(self.header()["originator"], "claude-cli")


class EndToEndShimTest(unittest.TestCase):
    """Run the OLD entry point (hook_bridge.py) as a subprocess in an isolated HOME for each host."""
    def run_event(self, env_extra):
        with tempfile.TemporaryDirectory() as t:
            home = Path(os.path.realpath(t)); cc = home / ".evolving-profile" / "claude-code"; cc.mkdir(parents=True)
            for name in ("hook_bridge.py", "hook_bridge_desktop.py", "desktop_rollout.py"):
                (cc / name).write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "EP_"))}
            env.update({"HOME": str(home), **env_extra})
            p = subprocess.run([sys.executable, str(cc / "hook_bridge.py"), "pretool"], input=json.dumps(
                {"session_id": str(uuid.uuid4()), "tool_name": "Read", "hook_event_name": "PreToolUse"}), text=True, capture_output=True, env=env, timeout=30)
            log = [json.loads(l) for l in (cc / "desktop-hook.log").read_text(encoding="utf-8").splitlines()]
            return p, log[-1]

    def test_cli_entrypoint_through_the_shim(self):
        p, rec = self.run_event({"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertEqual(p.returncode, 0, p.stderr); self.assertEqual((rec["host"], rec["entrypoint"], rec["event"]), ("claude-cli", "cli", "pretool"))

    def test_desktop_entrypoint_through_the_shim(self):
        p, rec = self.run_event({"CLAUDE_CODE_ENTRYPOINT": "local-agent", "CLAUDE_CODE_IS_COWORK": "1"})
        self.assertEqual(p.returncode, 0, p.stderr); self.assertEqual(rec["host"], "claude-desktop")

    def test_unknown_entrypoint_is_logged_and_safe(self):
        p, rec = self.run_event({"CLAUDE_CODE_ENTRYPOINT": "brand-new-surface"})
        self.assertEqual(p.returncode, 0); self.assertEqual((rec["host"], rec["entrypoint"]), ("claude-code", "brand-new-surface"))

    def test_garbage_stdin_never_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            home = Path(os.path.realpath(t)); cc = home / ".evolving-profile" / "claude-code"; cc.mkdir(parents=True)
            for name in ("hook_bridge.py", "hook_bridge_desktop.py", "desktop_rollout.py"):
                (cc / name).write_text((ROOT / name).read_text(encoding="utf-8"), encoding="utf-8")
            p = subprocess.run([sys.executable, str(cc / "hook_bridge.py"), "recall"], input="{not json", text=True, capture_output=True, env={**os.environ, "HOME": str(home)}, timeout=30)
            self.assertEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
