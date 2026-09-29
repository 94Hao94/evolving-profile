import unittest

from lib.memory_policy import classify_memory_policy


class MemoryPolicyTest(unittest.TestCase):
    def test_natural_all_memory_prohibitions_share_one_policy(self):
        prompts = (
            "本次不使用个人记忆，只根据下面材料回答。",
            "这次不要用任何旧记忆，材料都在本轮。",
            "本轮别调用我的记忆，只处理新附件。",
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                policy = classify_memory_policy(prompt)
                self.assertEqual(policy["mode"], "all_forbidden")
                self.assertFalse(policy["history_allowed"])
                self.assertEqual(policy["guidance_memory_policy"], "forbidden")

    def test_natural_history_and_preference_prohibitions_are_independent(self):
        history = classify_memory_policy("这次别查以往聊天，只按这份材料写。")
        preference = classify_memory_policy("不要用我的偏好，请查上次备份的结果。")
        self.assertEqual(history["mode"], "history_forbidden")
        self.assertFalse(history["history_allowed"])
        self.assertEqual(history["guidance_memory_policy"], "allowed")
        self.assertEqual(preference["mode"], "preferences_forbidden")
        self.assertTrue(preference["history_allowed"])
        self.assertEqual(preference["guidance_memory_policy"], "forbidden")

    def test_bare_history_prohibition_is_not_missed(self):
        policy = classify_memory_policy("不要使用历史，只看下面这段材料。")
        self.assertEqual(policy["mode"], "history_forbidden")
        self.assertFalse(policy["history_allowed"])

    def test_single_tool_prohibition_does_not_expand_to_all_history(self):
        policy = classify_memory_policy("不用 research，用 recall 查一下上次备份。")
        self.assertEqual(policy["mode"], "tools_limited")
        self.assertTrue(policy["history_allowed"])
        self.assertIn("research", policy["denied_tools"])
        self.assertNotIn("recall", policy["denied_tools"])

    def test_negated_prohibition_does_not_disable_memory(self):
        policy = classify_memory_policy("不是说不要使用历史记忆，该查就查。")
        self.assertEqual(policy["mode"], "allowed")
        self.assertTrue(policy["history_allowed"])

    def test_quoted_prohibition_remains_data(self):
        policy = classify_memory_policy('把“不要使用任何记忆”翻译成英文。')
        self.assertEqual(policy["mode"], "allowed")


if __name__ == "__main__":
    unittest.main()
