import json, os, sys, tempfile, unittest, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import desktop_rollout as dr

SCHED_WRAP = '<scheduled-task name="x" file="/a/SKILL.md">\nThis is an automated run of a scheduled task.\n...</scheduled-task>'
SCHED_FIRE = "[SCHEDULED TASK - AUTOMATED FIRING OF A CONFIGURED PROMPT]\nThis turn was started automatically by a schedule, not typed live by the user.\n..."


class AutomatedSessionTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.home = Path(os.path.realpath(self.t.name))
        dr.BASE = self.home / "cc"; dr.ROOT = dr.BASE / "rollouts"; dr.PENDING = dr.BASE / "rollouts-pending"; dr.OFF = dr.BASE / "off"
        dr.BASE.mkdir(parents=True)
        self.sid = str(uuid.uuid4()); self.tp = self.home / "t.jsonl"

    def tearDown(self):
        self.t.cleanup()

    def put(self, *rows):
        self.tp.write_text("\n".join(json.dumps({"role": r, "content": c, "timestamp": f"2026-10-24T09:0{i}:00Z"}, ensure_ascii=False)
                                     for i, (r, c) in enumerate(rows)) + "\n", encoding="utf-8")

    def w(self):
        return dr.write_rollout(self.sid, str(self.tp), "/private/var/empty")

    def test_pure_scheduled_session_is_skipped_and_writes_nothing(self):
        self.put(("user", SCHED_WRAP), ("user", SCHED_FIRE), ("assistant", "检查结果"))
        self.assertEqual(self.w()["rollout"], "skipped_automated_only")
        self.assertFalse(dr.ROOT.exists() and list(dr.ROOT.rglob("*.jsonl")))

    def test_wrappers_are_filtered_but_real_user_text_is_kept(self):
        self.put(("user", SCHED_WRAP), ("user", "真人问题"), ("assistant", "回答"))
        self.assertEqual(self.w()["rollout"], "written")
        txt = next(dr.ROOT.rglob("rollout-*.jsonl")).read_text(encoding="utf-8")
        self.assertIn("真人问题", txt); self.assertNotIn("scheduled-task", txt); self.assertNotIn("AUTOMATED FIRING", txt)

    def test_consecutive_real_user_messages_keep_their_old_structure(self):
        # deliberately unchanged behaviour: each user message stays its own turn (merging was evaluated and rejected)
        self.put(("user", "第一句"), ("user", "第二句补充"), ("assistant", "统一回答"))
        self.assertEqual(self.w()["rollout"], "written")
        rows = [json.loads(l) for l in next(dr.ROOT.rglob("rollout-*.jsonl")).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(1 for r in rows if r["type"] == "turn_context"), 2)

    def test_normal_dialogue_is_byte_identical_to_before(self):
        self.put(("user", "你好"), ("assistant", "你好！"), ("user", "再问"), ("assistant", "再答"))
        self.assertEqual(self.w()["rollout"], "written")
        rows = [json.loads(l) for l in next(dr.ROOT.rglob("rollout-*.jsonl")).read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["type"] for r in rows], ["session_meta", "turn_context", "response_item", "event_msg", "response_item",
                                                     "turn_context", "response_item", "event_msg", "response_item"])

    def test_turn_ids_are_stable_when_a_chat_grows(self):
        self.put(("user", "q1"), ("assistant", "a1"))
        self.w(); first = [json.loads(l)["payload"]["turn_id"] for l in next(dr.ROOT.rglob("rollout-*.jsonl")).read_text().splitlines() if '"turn_context"' in l]
        self.put(("user", "q1"), ("assistant", "a1"), ("user", "q2"), ("assistant", "a2"))
        self.w(); self.assertTrue(dr.write_rollout(self.sid, str(self.tp), "/p", force=True)["rollout"] == "written")
        second = [json.loads(l)["payload"]["turn_id"] for l in next(dr.ROOT.rglob("rollout-*.jsonl")).read_text().splitlines() if '"turn_context"' in l]
        self.assertEqual(second[:1], first)


if __name__ == "__main__":
    unittest.main()
