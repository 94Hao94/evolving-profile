import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))

from raw_preference_pipeline import clean_user_text, reviewable_message


class RawPreferencePipelineTests(unittest.TestCase):
    def test_removes_generated_trainer_context_before_candidate_review(self):
        source = "[TRAINER_AUTOMATIC_NEXT_CONTEXT]系统要求[/TRAINER_AUTOMATIC_NEXT_CONTEXT]\n用户要保留原话"
        self.assertEqual(clean_user_text(source), "用户要保留原话")

    def test_keeps_short_explicit_corrections_for_entity_review(self):
        self.assertTrue(reviewable_message("不是巨神，是具身"))
