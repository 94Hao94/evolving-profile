import unittest


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
