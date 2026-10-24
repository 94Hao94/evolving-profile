import json, os, tempfile, unittest, uuid, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.session_paths import session_roots
from lib.context_incremental import ContextIncremental


class DesktopRootTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.home = Path(os.path.realpath(self.t.name))      # realpath: codec rejects symlinked parents (/tmp -> /private/tmp)

    def tearDown(self):
        self.t.cleanup()

    def test_real_codex_layout_includes_desktop_rollouts(self):
        roots = session_roots(self.home / ".codex" / "sessions")
        self.assertEqual(roots, [self.home / ".codex" / "sessions", self.home / ".codex" / "archived_sessions",
                                 self.home / ".evolving-profile" / "claude-code" / "rollouts"])

    def test_other_roots_are_untouched(self):
        self.assertEqual(session_roots(self.home / "sessions"), [self.home / "sessions", self.home / "archived_sessions"])
        self.assertEqual(session_roots(self.home / "elsewhere"), [self.home / "elsewhere"])
        self.assertEqual(session_roots(self.home / ".codex" / "other"), [self.home / ".codex" / "other"])

    def test_discovery_sees_a_converted_desktop_session_and_keeps_codex(self):
        import desktop_rollout as dr
        cs = str(uuid.uuid4()); cdir = self.home / ".codex" / "sessions" / "2026" / "10" / "23"; cdir.mkdir(parents=True)
        (cdir / f"rollout-2026-10-23T10-00-00-{cs}.jsonl").write_text(json.dumps(
            {"timestamp": "2026-10-23T10:00:00.000Z", "type": "session_meta",
             "payload": {"id": cs, "cwd": "/work", "timestamp": "2026-10-23T10:00:00.000Z"}}) + "\n")
        ds = str(uuid.uuid4())
        dr.ROOT = self.home / ".evolving-profile" / "claude-code" / "rollouts"; dr.OFF = self.home / "off"
        tp = self.home / "t.jsonl"
        tp.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [
            {"role": "user", "content": "桌面端的一句话", "timestamp": "2026-10-23T14:06:00Z"},
            {"role": "assistant", "content": "桌面端的回答", "timestamp": "2026-10-23T14:06:05Z"}]) + "\n")
        self.assertEqual(dr.write_rollout(ds, str(tp), "/private/var/empty")["rollout"], "written")
        w = ContextIncremental(str(self.home / "state"), str(self.home / ".codex" / "sessions"), debounce=0,
                               bank_id="test-bank", session_ids=None, new_after=None)
        d = w.discover(limit=64)
        self.assertEqual(d["source_sessions"], 2)
        self.assertEqual(d["valid_headers"], 2)
        for k in ("oversized_headers", "unparseable_headers", "incomplete_headers", "unreadable_headers",
                  "identity_mismatch_headers", "invalid_header_type"):
            self.assertEqual(d[k], 0, k)


if __name__ == "__main__":
    unittest.main()
