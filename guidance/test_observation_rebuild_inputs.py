import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))

import observation_rebuild


class ObservationInputTests(unittest.TestCase):
    def test_fetch_inputs_reads_every_page_and_rejects_cross_page_duplicates(self):
        requested = []

        def fake_get(path: str, timeout: int = 30):
            requested.append(path)
            if "offset=0" in path:
                return {"items": [{"id": "one"}, {"id": "two"}], "total": 3}
            return {"items": [{"id": "three"}], "total": 3}

        self.assertEqual([row["id"] for row in observation_rebuild.fetch_inputs(page_size=2, get_fn=fake_get)], ["one", "two", "three"])
        self.assertEqual(len(requested), 2)

    def test_observation_fingerprint_changes_when_source_or_content_changes(self):
        original = {"id": "o-1", "text": "first", "updated_at": "2026-09-17T00:00:00Z", "source_memory_ids": ["m-1"]}
        changed = {**original, "text": "corrected"}

        self.assertNotEqual(observation_rebuild.observation_fingerprint(original), observation_rebuild.observation_fingerprint(changed))

