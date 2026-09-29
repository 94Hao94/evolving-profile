"""Exercise complete Hook stdout, transport budget, policies and occurrence receipts."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import guidance_entry
import recall
from lib.context_summary import build_session_context, write_context_index
from lib.instruction_entry import CORE_TEXT, VERSION


class ManualEntryIntegrationTest(unittest.TestCase):
    def setUp(self):
        isolated=tempfile.TemporaryDirectory()
        self.addCleanup(isolated.cleanup)
        self.root=Path(isolated.name)
        self.calls=[]
        cfg=recall.load_config()
        cfg.update(autoRecall=False,agentOwnedGuidance=True,
                   promptIngressAuditPath=str(self.root/'ingress.jsonl'),
                   hookOutputReceiptRoot=str(self.root/'audit/hook-output-receipts'))
        class Response:
            def __enter__(inner):return inner
            def __exit__(inner,*args):return False
            def read(inner,*args):
                return json.dumps({'results':[{'id':'00000000-0000-0000-0000-000000000001','text':'一次有来源的候选摘要。'}]}).encode()
        def transport(request,timeout):
            self.calls.append(json.loads(request.data))
            return Response()
        packet={'included':[{'id':'pref-test','text':'明确完成状态和来源。','applies_when':['历史盘点'],'exceptions':['当前要求优先']}],'coverage':'complete_active_set'}
        for patcher in (
            patch.dict(os.environ,{'EVOLVING_PROFILE_STATE_ROOT':str(self.root),'EVOLVING_PROFILE_EXECUTION_MODE':''}),
            patch.object(recall,'load_config',return_value=cfg),
            patch.object(recall,'persist_hook_state',return_value=None),
            patch.object(recall,'post_memory_feedback',return_value=True),
            patch.object(recall,'ham_emit',return_value={}),
            patch.object(recall,'get_api_url',side_effect=AssertionError('legacy Controller entered')),
            patch.object(recall.urllib.request,'urlopen',side_effect=transport),
            patch.object(guidance_entry,'_call_preference',return_value=packet),
            patch.object(guidance_entry,'build_navigation_map',return_value=('<evolving_profile_navigation_map>测试目录</evolving_profile_navigation_map>',{})),
            patch.object(guidance_entry,'TASK_STATE_ROOT',self.root/'tasks'),
            patch.object(guidance_entry,'PROMPT_INGRESS',self.root/'ingress.jsonl'),
            patch.object(guidance_entry,'RECEIPT_ROOT',self.root/'entries'),
        ):
            patcher.start();self.addCleanup(patcher.stop)

    def run_prompt(self,prompt,**extra):
        output=io.StringIO()
        with patch.object(recall.sys,'stdin',io.StringIO(json.dumps({'prompt':prompt,'session_id':'isolated','turn_id':'test',**extra}))),contextlib.redirect_stdout(output):
            recall.main()
        return json.loads(output.getvalue())['hookSpecificOutput']['additionalContext']

    def test_monthly_inventory_has_direct_research_route_and_visible_preferences(self):
        context=self.run_prompt('我最近一个月都干什么了，分几类')
        self.assertIn('"recommended_route": "research"',context)
        self.assertIn('pref-test',context)
        self.assertEqual(context.count('<evolving_profile_memory_use_instruction '),1)
        self.assertEqual(context.count('<evolving_profile_memory_route>'),1)
        self.assertEqual(len(self.calls),0)
        receipts=list((self.root/'audit/hook-output-receipts/production').glob('*.json'))
        self.assertEqual(len(receipts),1)
        row=json.loads(receipts[0].read_text())
        self.assertEqual(row['system_probe']['actor'],'system_probe')
        self.assertEqual(row['system_probe']['returned_count'],0)
        self.assertEqual(row['system_probe']['reason'],'agent_query')
        self.assertLessEqual(row['system_probe']['context_tokens'],500)
        self.assertEqual(len((self.root/'ingress.jsonl').read_text().splitlines()),1)

    def test_self_contained_prompts_get_manual_without_bank_calls(self):
        for prompt in ('17乘以23等于多少？','解释一下 recall 和 research 的区别','你好'):
            context=self.run_prompt(prompt)
            self.assertIn(CORE_TEXT,context)
            self.assertIn(VERSION,context)
            self.assertNotIn('<evolving_profile_system_probe>',context)
        self.assertEqual(self.calls,[])

    def test_explicit_history_prohibitions_never_retrieve(self):
        for prompt in ('不要使用任何记忆和偏好，只看这段文字：备份。','不要使用历史事实，只看当前材料；但可以遵循我的协作偏好。'):
            context=self.run_prompt(prompt)
            self.assertNotIn('<evolving_profile_system_probe>',context)
        self.assertEqual(self.calls,[])

    def test_scenario_summary_is_not_preinjected_even_when_history_is_allowed(self):
        path = self.root / 'context-index.json'
        session = build_session_context('isolated', '', ['source-1'], 'PRIVATE_SCENARIO_MARKER')
        write_context_index(path, [session], [])
        with patch.dict(os.environ, {'EVOLVING_PROFILE_CONTEXT_INDEX': str(path)}):
            forbidden = self.run_prompt('不要使用任何旧记忆，只根据当前材料回答。')
            allowed = self.run_prompt('请查一下以前的备份决定。')
        self.assertNotIn('PRIVATE_SCENARIO_MARKER', forbidden)
        self.assertNotIn('PRIVATE_SCENARIO_MARKER', allowed)
        self.assertNotIn('<evolving_profile_context_navigation>', forbidden)
        self.assertNotIn('<evolving_profile_context_navigation>', allowed)

    def test_preference_prohibition_does_not_disable_history(self):
        context=self.run_prompt('不要使用我的偏好，请回顾上次备份最后是否成功。')
        self.assertNotIn('pref-test',context)
        self.assertEqual(len(self.calls),1)

    def test_elaborated_followup_searches_the_original_task(self):
        self.run_prompt('我最近一个月都干什么了，分几类')
        self.run_prompt('为什么没用research和recall这些？')
        context=self.run_prompt('那你用啊，每一类把做的事情也列出来')
        self.assertIn('"recommended_route": "research"',context)
        self.assertEqual(self.calls,[])

    def test_quoted_prohibition_is_data_not_instruction(self):
        self.assertFalse(recall.explicit_no_history_request('把“不要使用历史记忆”翻译成英文。'))


if __name__ == '__main__':unittest.main()
