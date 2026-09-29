import io
import json
import os
import tempfile
import unittest
import time
from contextlib import redirect_stdout
from unittest.mock import patch

import pre_tool_use
import recall
from memory_turn_check import local_memory_access_guard, observe_tool, register_route


class PreToolUseMemoryGuardTest(unittest.TestCase):
    def test_guard_retries_a_transient_missing_receipt(self):
        calls = []
        def guard(_hook):
            calls.append(True)
            return "EP 回执暂缺" if len(calls) == 1 else None
        with patch.object(pre_tool_use, "local_memory_access_guard", guard, create=True), \
             patch.object(pre_tool_use.time, "sleep"):
            result = pre_tool_use.guard_with_retry({"tool_name": "exec"}, attempts=2)
        self.assertIsNone(result)
        self.assertEqual(len(calls), 2)

    def test_missing_receipt_reason_is_distinguished_from_policy_block(self):
        with tempfile.TemporaryDirectory() as root:
            hook = {"tool_name": "exec", "session_id": "s", "turn_id": "t",
                    "tool_input": {"command": "rg x /tmp/evolving-profile-user/.codex/memories/MEMORY.md"}}
            reason = local_memory_access_guard(hook, root=root)
        self.assertIn("回执暂缺", reason)

    def test_shell_search_of_codex_memory_is_blocked_without_ep_route_receipt(self):
        hook = {
            "hook_event_name": "PreToolUse",
            "tool_name": "exec",
            "tool_use_id": "call-1",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "tool_input": {"command": "rg -n 优优 /tmp/evolving-profile-user/.codex/memories/MEMORY.md"},
        }
        output = io.StringIO()
        with patch.object(pre_tool_use, "load_config", return_value={}), \
             patch.object(pre_tool_use.sys, "stdin", io.StringIO(json.dumps(hook))), \
             redirect_stdout(output):
            pre_tool_use.main()

        self.assertIn('"permissionDecision":"deny"', output.getvalue().replace(" ", ""))
        self.assertIn("Evolving Profile", output.getvalue())

    def test_shell_command_that_only_mentions_memory_path_text_is_not_blocked(self):
        hook = {
            "hook_event_name": "PreToolUse",
            "tool_name": "exec",
            "tool_use_id": "call-mention-only",
            "session_id": "session-1",
            "turn_id": "turn-1",
            "tool_input": {"command": "python3 -c 'print(\"/.codex/memories\")'"},
        }
        output = io.StringIO()
        with patch.object(pre_tool_use, "load_config", return_value={}), \
             patch.object(pre_tool_use.sys, "stdin", io.StringIO(json.dumps(hook))), \
             redirect_stdout(output):
            pre_tool_use.main()

        self.assertEqual(output.getvalue(), "")

    def test_route_requires_the_exact_ep_tool_before_native_memory_can_be_used(self):
        with tempfile.TemporaryDirectory() as root:
            register_route({
                "invocation_id": "route-1", "session_id": "session-1", "turn_id": "turn-1",
                "raw_prompt": "我和天津农学院是什么关系？", "required_ep_tool": "mcp__evolving_profile_controller__recall",
                "allow_native_memory": False, "recommended_route": "recall",
            }, root=root)
            hook = {
                "tool_name": "exec", "session_id": "session-1", "turn_id": "turn-1",
                "tool_input": {"command": "rg 学校 /tmp/evolving-profile-user/.codex/memories/MEMORY.md"},
            }
            reason = local_memory_access_guard(hook, root=root)
            self.assertIn("mcp__evolving_profile_controller__recall", reason)

            observe_tool({
                "tool_name": "mcp__evolving_profile_controller__recall", "session_id": "session-1",
                "turn_id": "turn-1", "tool_use_id": "ep-call-1", "tool_input": {"query": "天津农学院关系"},
                "tool_response": {"content": [{"type": "text", "text": "{}"}]},
            }, root=root)
            self.assertIsNone(local_memory_access_guard(hook, root=root))

    def test_preference_route_requires_get_preference_not_recall(self):
        with tempfile.TemporaryDirectory() as root:
            register_route({
                "invocation_id": "route-2", "session_id": "session-1", "turn_id": "turn-2",
                "raw_prompt": "按我习惯记录的公文格式有哪些？", "required_ep_tool": "mcp__evolving_profile_controller__get_preference",
                "allow_native_memory": False, "recommended_route": "get_preference",
            }, root=root)
            hook = {"tool_name": "exec", "session_id": "session-1", "turn_id": "turn-2",
                    "tool_input": {"command": "rg 格式 /tmp/evolving-profile-user/.codex/memories/MEMORY.md"}}
            observe_tool({"tool_name": "mcp__evolving_profile_controller__recall", "session_id": "session-1",
                          "turn_id": "turn-2", "tool_use_id": "wrong-tool", "tool_response": {"content": []}}, root=root)
            self.assertIn("get_preference", local_memory_access_guard(hook, root=root))
            observe_tool({"tool_name": "mcp__evolving_profile_controller__get_preference", "session_id": "session-1",
                          "turn_id": "turn-2", "tool_use_id": "right-tool", "tool_response": {"content": [{"type": "text", "text": "{}"}]}}, root=root)
            self.assertIsNone(local_memory_access_guard(hook, root=root))

    def test_explicit_request_for_native_codex_memory_allows_local_read(self):
        with tempfile.TemporaryDirectory() as root:
            register_route({
                "invocation_id": "route-3", "session_id": "session-1", "turn_id": "turn-3",
                "raw_prompt": "请搜索 Codex 原生 Memory 里的内容", "required_ep_tool": "mcp__evolving_profile_controller__recall",
                "allow_native_memory": True, "recommended_route": "recall",
            }, root=root)
            hook = {"tool_name": "exec", "session_id": "session-1", "turn_id": "turn-3",
                    "tool_input": {"command": "rg 记忆 /tmp/evolving-profile-user/.codex/memories/MEMORY.md"}}
            self.assertIsNone(local_memory_access_guard(hook, root=root))

    def test_user_prompt_hook_registers_required_ep_tool_before_shell_fallback(self):
        prompt='我说公文和方案里面的格式，你这根据我习惯和要求记录的都有哪几种？'
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'HINDSIGHT_TURN_CHECK_ROOT':root,'EVOLVING_PROFILE_STATE_ROOT':root}), \
             patch.object(recall, 'record_prompt_ingress'), patch.object(recall, 'emit_hook_output'), \
             patch.object(recall, 'is_shadow_replay', return_value=False), \
             patch('system_probe.run_probe', return_value=('', {'state':'skipped','calls':0,'candidate_count':None,'returned_count':0,'items':[]})):
            recall.emit_bounded_system_probe(
                {'session_id':'session-2','turn_id':'turn-2','memory_prompt_origin':'user_direct'},
                prompt, {}, 'hook-check-2',
            )
            reason=local_memory_access_guard({
                'tool_name':'exec','session_id':'session-2','turn_id':'turn-2',
                'tool_input':{'command':'rg 格式 /tmp/evolving-profile-user/.codex/memories/MEMORY.md'},
            },root=root)
        self.assertIn('get_preference',reason)


if __name__ == "__main__":
    unittest.main()
