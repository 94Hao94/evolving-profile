import importlib.util
import unittest
from pathlib import Path


def _module():
    path = Path(__file__).with_name("evolving_profile_status_server.py")
    spec = importlib.util.spec_from_file_location("status_projection_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StatusProjectionSizeTest(unittest.TestCase):
    def test_list_projection_keeps_delivery_evidence_without_candidate_bodies(self):
        """A 10-second status refresh must not serialize megabytes of controller candidates."""
        module = _module()
        trace = {
            "execution_id": "execution-1",
            "raw_user_prompt": "请检查链路",
            "query_preview": "请检查链路",
            "memory_effectiveness": {
                "injected_count": 1,
                "injected_ids": ["memory-1"],
                "items": [{"id": "candidate-1", "text": "x" * 200_000, "injected": False}],
            },
            "pipeline_stages": {"controller_admission": {"candidate_items": [{"text": "y" * 200_000}]}},
        }

        projected = module.trace_list_projection(trace)

        self.assertEqual(projected["memory_effectiveness"]["injected_ids"], ["memory-1"])
        self.assertNotIn("items", projected["memory_effectiveness"])
        self.assertNotIn("pipeline_stages", projected)
        self.assertLess(len(str(projected)), 10_000)


if __name__ == "__main__":
    unittest.main()
