import unittest
import importlib.util
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ep_controller_receipt_contract',ROOT/'host-adapter/evolving_profile_controller_mcp.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


def assert_bound_route_receipt(receipt):
    binding = receipt.get("prompt_binding") or {}
    check_id = receipt.get("check_id")
    assert check_id
    assert binding.get("hook_invocation_id") == check_id
    assert binding.get("session_id")
    assert binding.get("turn_id")
    events = receipt.get("tool_events") or []
    assert events and events[0].get("tool") == "memory_check"
    assert any(event.get("tool") in {"recall", "research"} for event in events[1:])
    for event in events:
        assert event.get("tool")
        assert "returned_count" in event


class RouteReceiptContractTest(unittest.TestCase):
    def test_multi_route_coverage_exposes_skipped_and_unverified_channels(self):
        receipt={
            'history_plan': {'mandatory_history_tools':['user_recall','agent_recall','audit_thread_history']},
            'tool_events':[{'tool':'agent_recall','returned_count':8,'source_read_count':0}],
        }
        module._route_receipt_counts(receipt)
        self.assertEqual(receipt['coverage_contract']['candidate_state'],'candidate_unverified')
        self.assertEqual(receipt['coverage_contract']['channels_checked'],['agent_recall'])
        self.assertEqual(receipt['coverage_contract']['channels_skipped'],['user_recall','audit_thread_history'])

    def test_empty_history_call_is_distinguished_from_not_retrieved(self):
        receipt={'history_plan': {'mandatory_history_tools':['user_recall']}, 'tool_events':[{'tool':'user_recall','returned_count':0}]}
        module._route_receipt_counts(receipt)
        self.assertEqual(receipt['coverage_contract']['candidate_state'],'retrieved_no_candidate')

    def test_memory_check_and_history_tools_share_prompt_binding(self):
        assert_bound_route_receipt(
            {
                "check_id": "prompt-123",
                "prompt_binding": {
                    "hook_invocation_id": "prompt-123",
                    "session_id": "session-1",
                    "turn_id": "turn-1",
                },
                "tool_events": [
                    {"tool": "memory_check", "returned_count": 0},
                    {
                        "tool": "research",
                        "returned_count": 6,
                        "candidate_count": 21,
                        "next_offset": 6,
                    },
                ],
            }
        )


if __name__ == "__main__":
    unittest.main()
