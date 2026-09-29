import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent))

from guidance_worker import changed_observation_ids


class GuidanceWorkerTests(unittest.TestCase):
    def test_legacy_id_only_watermark_processes_only_new_observations_once(self):
        current = {"old": "sha256:old", "new": "sha256:new"}
        state = {"seen_observation_ids": ["old"]}

        self.assertEqual(changed_observation_ids(current, state), ["new"])

    def test_fingerprint_watermark_reprocesses_a_changed_observation(self):
        current = {"unchanged": "sha256:a", "changed": "sha256:new"}
        state = {"seen_observation_fingerprints": {"unchanged": "sha256:a", "changed": "sha256:old"}}

        self.assertEqual(changed_observation_ids(current, state), ["changed"])
