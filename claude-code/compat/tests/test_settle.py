import json, os, sys, tempfile, time, unittest, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import desktop_rollout as dr


class SettleTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.home = Path(os.path.realpath(self.t.name))
        dr.BASE = self.home / "cc"; dr.ROOT = dr.BASE / "rollouts"; dr.PENDING = dr.BASE / "rollouts-pending"; dr.OFF = dr.BASE / "off"
        dr.BASE.mkdir(parents=True)
        self.sid = str(uuid.uuid4()); self.tp = self.home / "t.jsonl"; self.n = 0
        self.turn()

    def tearDown(self):
        self.t.cleanup()

    def turn(self):
        self.n += 1
        with open(self.tp, "a", encoding="utf-8") as f:
            f.write(json.dumps({"role": "user", "content": f"问题{self.n}", "timestamp": f"2026-10-23T14:{self.n:02d}:00Z"}, ensure_ascii=False) + "\n")
            f.write(json.dumps({"role": "assistant", "content": f"回答{self.n}", "timestamp": f"2026-10-23T14:{self.n:02d}:05Z"}, ensure_ascii=False) + "\n")

    def rollout(self):
        return next(dr.ROOT.rglob("rollout-*.jsonl"))

    def age(self, seconds):
        p = self.rollout(); t = time.time() - seconds; os.utime(p, (t, t))

    def pending(self):
        return sorted(p.name for p in dr.PENDING.glob("*.json")) if dr.PENDING.is_dir() else []

    def w(self, **kw):
        return dr.write_rollout(self.sid, str(self.tp), "/private/var/empty", **kw)

    def test_first_write_is_immediate_and_leaves_no_marker(self):
        self.assertEqual(self.w()["rollout"], "written"); self.assertEqual(self.pending(), [])

    def test_update_inside_settle_is_deferred_and_file_untouched(self):
        self.w(); before = self.rollout().read_bytes(); self.turn()
        r = self.w()
        self.assertEqual(r["rollout"], "deferred"); self.assertGreater(r["settle_remaining_s"], 0)
        self.assertEqual(self.rollout().read_bytes(), before)
        self.assertEqual(self.pending(), [f"{self.sid}.json"])
        self.assertEqual(len(list(dr.ROOT.rglob("*"))), len(list(dr.ROOT.rglob("*"))))        # markers live outside the discovered root
        self.assertFalse(list(dr.ROOT.rglob("*.json")))

    def test_update_after_settle_is_written_and_marker_cleared(self):
        self.w(); self.turn(); self.assertEqual(self.w()["rollout"], "deferred")
        self.age(dr.SETTLE + 60)
        self.assertEqual(self.w()["rollout"], "written"); self.assertEqual(self.pending(), [])
        self.assertEqual(sum(1 for _ in open(self.rollout(), "rb") if b'"turn_context"' in _), 2)

    def test_identical_content_is_unchanged_not_deferred(self):
        self.w(); self.assertEqual(self.w()["rollout"], "unchanged"); self.assertEqual(self.pending(), [])

    def test_flush_pending_waits_until_quiet_then_writes(self):
        self.w(); self.turn(); self.w(); self.turn(); self.w()
        self.assertEqual(self.pending(), [f"{self.sid}.json"])           # one marker per session, not per turn
        self.assertEqual(dr.flush_pending(), 0); self.assertEqual(len(self.pending()), 1)   # still settling
        self.age(dr.SETTLE + 60)
        self.assertEqual(dr.flush_pending(), 1); self.assertEqual(self.pending(), [])
        self.assertEqual(sum(1 for _ in open(self.rollout(), "rb") if b'"turn_context"' in _), 3)   # all turns present

    def test_force_bypasses_settle(self):
        self.w(); self.turn()
        self.assertEqual(self.w(force=True)["rollout"], "written")

    def test_kill_switch_blocks_write_and_flush(self):
        self.w(); self.turn(); self.w(); self.age(dr.SETTLE + 60)
        dr.OFF.write_text("x")
        self.assertEqual(self.w()["rollout"], "disabled_by_switch"); self.assertEqual(dr.flush_pending(), 0)
        self.assertEqual(sum(1 for _ in open(self.rollout(), "rb") if b'"turn_context"' in _), 1)

    def test_corrupt_marker_is_dropped_without_crashing(self):
        dr.PENDING.mkdir(parents=True); (dr.PENDING / "junk.json").write_text("{not json")
        self.assertEqual(dr.flush_pending(), 0); self.assertEqual(self.pending(), [])

    def test_marker_for_vanished_transcript_is_dropped(self):
        self.w(); self.turn(); self.w(); self.age(dr.SETTLE + 60); self.tp.unlink()
        self.assertEqual(dr.flush_pending(), 0); self.assertEqual(self.pending(), [])


if __name__ == "__main__":
    unittest.main()
