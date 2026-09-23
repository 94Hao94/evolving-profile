import json
import os
import subprocess
import unittest
from pathlib import Path


class McpToolCatalogTest(unittest.TestCase):
    def test_runtime_recovery_tool_is_listed_and_callable(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env.update({
            "PYTHONPATH": ":".join(str(root / part) for part in ("host-adapter", "guidance", "controller", "ham-os")),
            "EVOLVING_PROFILE_GUIDANCE_SRC": str(root / "guidance"),
            "EVOLVING_PROFILE_GUIDANCE_CONFIG": str(Path.home() / ".evolving-profile/guidance-v1/guidance-v1.json"),
        })
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "refresh_runtime_guidance", "arguments": {
                "task": {"objective": "恢复视觉验收", "current_user_message": "恢复视觉验收", "phase": "verify"},
                "runtime_event": {"capability": "computer_use", "failure": "transport_closed", "occurrence": 1, "required_for": "visual_acceptance"},
            }}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_preference", "arguments": {
                "memory_policy": "allowed", "loaded": [], "task": {"objective": "偏好", "phase": "understand", "current_constraints": [], "domains": [], "media": [], "resolved_entities": [], "unresolved_references": []},
            }}},
        ]
        completed = subprocess.run(
            [str(Path.home() / ".evolving-profile/runtime/python-3.11/bin/python"), str(root / "host-adapter/evolving_profile_controller_mcp.py")],
            input="\n".join(json.dumps(item) for item in requests) + "\n",
            text=True,
            capture_output=True,
            env=env,
            timeout=20,
            check=True,
        )
        rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        tools = {item["name"] for item in next(row for row in rows if row.get("id") == 2)["result"]["tools"]}
        self.assertIn("refresh_runtime_guidance", tools)
        self.assertTrue({'catalog_list','catalog_search','catalog_read','record_evidence_decision','update_task_state'} <= tools)
        preference = next(item for item in next(row for row in rows if row.get("id") == 2)["result"]["tools"] if item["name"] == "get_preference")
        self.assertIn("check_id", preference["inputSchema"]["required"])
        self.assertEqual(preference["inputSchema"]["properties"]["check_id"]["type"], "string")
        payload = json.loads(next(row for row in rows if row.get("id") == 3)["result"]["content"][0]["text"])
        self.assertEqual(payload["mode"], "runtime_guidance_refresh")
        self.assertEqual(payload["persistence"], "none_current_turn_only")
        error = next(row for row in rows if row.get("id") == 4)
        self.assertIn("requires the current Prompt check_id", error["error"]["message"])


if __name__ == "__main__":
    unittest.main()
