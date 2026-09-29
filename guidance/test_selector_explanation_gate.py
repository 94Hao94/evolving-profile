import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))

from selector import explanation_preference_requested


class ExplanationPreferenceGateTests(unittest.TestCase):
    def test_rejects_generic_ui_confusion_without_an_english_term(self):
        self.assertFalse(explanation_preference_requested("多维度偏好里待审核是怎么回事，链路图看不懂"))

    def test_accepts_an_explicit_request_to_explain_an_english_term(self):
        self.assertTrue(explanation_preference_requested("请解释 SVG、XML 和 API 分别是什么意思"))

    def test_accepts_a_direct_request_for_english_explanation(self):
        self.assertTrue(explanation_preference_requested("英文缩写和音标怎么解释"))
