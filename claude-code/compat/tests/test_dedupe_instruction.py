import os, sys, unittest
from pathlib import Path

CC = Path.home() / ".evolving-profile" / "claude-code"
sys.path.insert(0, str(CC))
import hook_bridge_desktop as h

BLK = '<evolving_profile_memory_use_instruction version="v1" sha256="abc" host="x">' + "长" * 4000 + '</evolving_profile_memory_use_instruction>'
CTX = '<ep_prompt_binding check_id="1">k</ep_prompt_binding>\n' + BLK + '\n<evolving_profile_memory_route>keep</evolving_profile_memory_route>'


class DedupeInstruction(unittest.TestCase):
    sid = "unittest-dedupe-sid"

    def setUp(self):
        os.environ.pop("EP_FULL_INSTRUCTION", None)
        m = h._marker(self.sid)
        if m.exists():
            m.unlink()
        self.addCleanup(lambda: h._marker(self.sid).exists() and h._marker(self.sid).unlink())

    def test_untouched_without_session_marker(self):
        self.assertEqual(h.dedupe_instruction("recall", self.sid, CTX), (CTX, 0))

    def test_session_event_never_stripped_and_sets_marker(self):
        self.assertEqual(h.dedupe_instruction("session", self.sid, CTX), (CTX, 0))
        self.assertTrue(h._marker(self.sid).exists())

    def test_recall_after_session_gets_stub_but_keeps_everything_else(self):
        h.dedupe_instruction("session", self.sid, CTX)
        c, saved = h.dedupe_instruction("recall", self.sid, CTX)
        self.assertGreater(saved, 3000)
        for keep in ('check_id="1"', "keep", 'version="v1" sha256="abc"'):
            self.assertIn(keep, c)
        self.assertNotIn("长", c)

    def test_kill_switch(self):
        h.dedupe_instruction("session", self.sid, CTX)
        os.environ["EP_FULL_INSTRUCTION"] = "1"
        self.assertEqual(h.dedupe_instruction("recall", self.sid, CTX), (CTX, 0))


if __name__ == "__main__":
    unittest.main()
