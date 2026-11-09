import json, os, sys, unittest

from evolving_profile_api.engine.retain import source_attribution as sa

META = {"source_attribution_required": "role_quote_v1"}
USER_A = "某校区监控提升改造项目，现部署视频监控点位454个，道闸与闸机均集中安装于学院南门。"
USER_B = "附件1-9是需要填写的材料和填写说明，你自己看着办哪些需要填，然后我告诉你具体要求。"
ASSIST = "我建议先保存配置，再重启服务并回读，最后做真实页面验收。"
ROWS = [{"role": "user", "content": USER_A}, {"role": "assistant", "content": ASSIST}, {"role": "user", "content": USER_B}]


def verify(quote, role="user", index=0, rows=ROWS, **extra):
    return sa.verify_attribution(json.dumps(rows, ensure_ascii=False),
                                 {"source_quote": quote, "source_role": role, "source_message_index": index, **extra}, META)


class QuoteRepairTest(unittest.TestCase):
    def setUp(self):
        os.environ.pop("EVOLVING_PROFILE_API_QUOTE_REPAIR", None)

    # ---- unchanged behaviour -------------------------------------------------------------------------------------------
    def test_exact_quote_at_right_index_is_untouched(self):
        canonical, fact_type, md = verify(USER_A)
        self.assertEqual(canonical, USER_A); self.assertEqual(fact_type, "world")
        self.assertNotIn("source_quote_repair", md); self.assertNotIn("source_quote_resolution", md)
        self.assertEqual(md["source_message_index"], "0")

    def test_role_lie_still_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "source_role_mismatch|source_quote"):
            verify(ASSIST, role="user", index=1)

    def test_nonexistent_quote_still_fails(self):
        with self.assertRaisesRegex(ValueError, "source_quote_not_in_original_message"):
            verify("用户说必须马上保存所有配置并且重启。")

    def test_unrelated_sentence_sharing_a_few_words_still_fails(self):
        with self.assertRaisesRegex(ValueError, "source_quote_not_in_original_message"):
            verify("某学校的食堂今天供应了很多种类的面食。")

    def test_selector_path_is_not_touched_by_repair(self):
        with self.assertRaisesRegex(ValueError, "source_quote_selector_invalid"):
            verify("", source_quote_ref="bogus:0:0:5")

    # ---- repair 1: wrong index, exact quote ---------------------------------------------------------------------------
    def test_exact_quote_with_wrong_index_is_corrected(self):
        canonical, _, md = verify(USER_B, index=0)                      # model said message 0, it is message 2
        self.assertEqual(canonical, USER_B)
        self.assertEqual(md["source_message_index"], "2")
        self.assertEqual(md["source_quote_resolution"], "repaired_exact_quote_index_corrected")
        self.assertEqual(json.loads(md["source_quote_repair"])["model_index"], 0)

    def test_exact_quote_present_in_two_messages_stays_ambiguous(self):
        rows = ROWS + [{"role": "user", "content": USER_B + "补充。"}]
        with self.assertRaises(ValueError):
            verify(USER_B, index=0, rows=rows)

    def test_wrong_index_never_crosses_authors(self):
        with self.assertRaises(ValueError):
            verify(ASSIST, role="user", index=0)                        # exists only in an assistant message

    # ---- repair 2: near-verbatim quote snapped to the real span -------------------------------------------------------
    def test_markup_and_punctuation_differences_are_snapped_to_exact_original(self):
        model = "某校区监控提升改造项目 现部署视频监控点位454个、道闸与闸机均集中安装于学院南门"   # punctuation altered
        canonical, _, md = verify(model)
        self.assertEqual(md["source_quote_resolution"], "repaired_snapped_to_verbatim_span")
        self.assertIn(canonical, USER_A)                                  # stored text is an exact substring of the source
        self.assertNotEqual(canonical, model)
        rep = json.loads(md["source_quote_repair"])
        self.assertGreaterEqual(rep["similarity"], 0.90)
        self.assertEqual(len(rep["model_quote_sha256"]), 64)
        self.assertEqual(md["source_quote"], canonical)

    def test_snap_keeps_the_claimed_author(self):
        near = "我建议先保存配置 再重启服务并回读 最后做真实页面验收"
        canonical, fact_type, md = verify(near, role="assistant", index=1)
        self.assertIn(ASSIST[:6], canonical)
        self.assertTrue(canonical.startswith("Assistant statement (not user-confirmed): "))
        self.assertEqual(fact_type, "experience"); self.assertEqual(md["independent_user_evidence"], "false")

    def test_two_equally_close_messages_fail_closed(self):
        rows = [{"role": "user", "content": USER_A}, {"role": "user", "content": USER_A.replace("454", "455")}]
        with self.assertRaisesRegex(ValueError, "source_quote_not_in_original_message"):
            verify("某校区监控提升改造项目，现部署视频监控点位45个，道闸与闸机均集中安装于学院南门。", rows=rows)

    def test_snap_refused_when_original_span_carries_pasted_line_numbers(self):
        # the model retyped the sentence without the `cat -n` numbers; snapping would store polluted text -> stays rejected
        polluted = [{"role": "user", "content": "LEADER = \"肖俊生\"; LEADER_TEL = \"13132129388\"\n76\tCONTACT = \"马木尔\"; CONTACT_TEL = \"15948352149\"\n77\tYEAR = 2026"}]
        model = "LEADER = \"肖俊生\"; LEADER_TEL = \"13132129388\"\nCONTACT = \"马木尔\"; CONTACT_TEL = \"15948352149\"\nYEAR = 2026"
        with self.assertRaisesRegex(ValueError, "source_quote_not_in_original_message"):
            verify(model, rows=polluted)

    def test_clean_markdown_difference_is_still_snapped(self):
        rows = [{"role": "assistant", "content": "**偏好条目的归属可能不对。** 这 4 条偏好的 user_id 是 alice，需要你确认后再套用。"}]
        canonical, _, md = verify("偏好条目的归属可能不对。 这 4 条偏好的 user_id 是 alice，需要你确认后再套用。", role="assistant", index=0, rows=rows)
        self.assertEqual(md["source_quote_resolution"], "repaired_snapped_to_verbatim_span")
        self.assertIn(md["source_quote"], rows[0]["content"])

    def test_kill_switch_restores_exact_only_behaviour(self):
        os.environ["EVOLVING_PROFILE_API_QUOTE_REPAIR"] = "0"
        with self.assertRaisesRegex(ValueError, "source_quote_not_in_original_message"):
            verify("某校区监控提升改造项目 现部署视频监控点位454个、道闸与闸机均集中安装于学院南门")
        with self.assertRaises(ValueError):
            verify(USER_B, index=0)

    def test_oversized_quote_is_not_attempted(self):
        long_quote = "某学校" * 400
        with self.assertRaises(ValueError):
            verify(long_quote)

    def test_snapped_span_is_unique_in_the_message(self):
        rows = [{"role": "user", "content": "甲乙丙丁戊己庚辛壬癸子丑寅卯。" * 3}]
        with self.assertRaises(ValueError):
            verify("甲乙丙丁戊己庚辛壬癸子丑寅卯", rows=rows)           # exact but repeated: stays ambiguous (unchanged behaviour)


if __name__ == "__main__":
    unittest.main()
