import sys
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guidance_entry import build_request, prepare_agent_owned_entry
import guidance_entry


class GuidanceEntryRequestTest(unittest.TestCase):
    def test_actual_output_contains_every_receipted_candidate_and_one_manual(self):
        candidate={'id':'candidate-unique-delivery','revision':'v1','text':'复核完成状态必须有来源。','applies_when':['历史盘点'],'exceptions':['当前要求优先']}
        packet={'included':[candidate],'preference_candidates':[candidate],'coverage':'complete_active_set'}
        with tempfile.TemporaryDirectory() as root, patch.object(guidance_entry,'TASK_STATE_ROOT',Path(root)/'state'), patch.object(guidance_entry,'RECEIPT_ROOT',Path(root)/'receipts'), patch.object(guidance_entry,'_call_preference',return_value=packet):
            result=prepare_agent_owned_entry({'session_id':'delivery','hook_invocation_id':'delivery'},'我最近一个月都干什么了，分几类')
        self.assertEqual(result['receipt']['entry_context_included_count'],1)
        self.assertIn(candidate['id'],result['context'])
        self.assertIn(candidate['text'],result['context'])
        self.assertEqual(result['context'].count('<evolving_profile_memory_use_instruction '),1)
        self.assertNotIn('<evolving_profile_memory_u\n',result['context'])

    def test_elaborated_followup_preserves_monthly_task(self):
        req=build_request({'memory_full_prompt':'当前任务：我最近一个月都干什么了，分几类'},'那你用啊，每一类把做的事情也列出来','test')
        self.assertTrue(req['task']['continuation'])
        self.assertIn('最近一个月',req['task']['context_summary'])
    def test_long_prompt_does_not_displace_navigation_or_break_hook_context(self):
        prompt='只改入口接线，保持深读判断由 Agent 完成。'*400
        with tempfile.TemporaryDirectory() as root, patch.object(guidance_entry,'TASK_STATE_ROOT',Path(root)/'task-state'), patch.object(guidance_entry,'RECEIPT_ROOT',Path(root)/'receipts'):
            result=prepare_agent_owned_entry({'session_id':'long','turn_id':'t1','hook_invocation_id':'long1'},prompt)
        self.assertLessEqual(len(result['context']),guidance_entry.AGENT_ENTRY_MAX_CONTEXT_CHARS)
        self.assertIn('</evolving_profile_navigation_map>',result['context'])
        self.assertIn('</evolving_profile_task_state>',result['context'])
        self.assertEqual(result['receipt']['task_state']['current_message'],prompt)

    def test_agent_owned_entry_provides_navigation_before_full_guidance_selection(self):
        with tempfile.TemporaryDirectory() as root, patch.object(guidance_entry,'TASK_STATE_ROOT',Path(root)/'task-state'), patch.object(guidance_entry,'RECEIPT_ROOT',Path(root)/'receipts'), patch.object(guidance_entry,'_call_preference',side_effect=AssertionError('private selector called')):
            result=prepare_agent_owned_entry({'session_id':'s1','turn_id':'t1','hook_invocation_id':'h1'},'那你建议怎么修？',memory_policy='allowed')
        self.assertEqual(result['receipt']['invocation_mode'],'navigation_plus_get_preference_candidate_packet')
        self.assertEqual(result['receipt']['included_count'],0)
        self.assertIn('get_preference',result['context'])
        self.assertIn('<evolving_profile_navigation_map',result['context'])
        self.assertNotIn('入口未读取私人偏好或Bank目录',result['context'])
        self.assertIn('那你建议怎么修',result['receipt']['task_state']['current_message'])

    def test_referential_repair_question_is_a_continuation(self):
        request = build_request(
            {"memory_full_prompt": "前一项活动任务：审查并修复 Evolving Profile 2.1"},
            "那你建议怎么修？", "entry:test",
        )
        self.assertTrue(request["task"]["continuation"])
        self.assertIn("Evolving Profile 2.1", request["task"]["context_summary"])

    def test_continuation_recovers_task_past_repeated_continue(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ingress.jsonl'
            path.write_text('\n'.join(json.dumps({'session_id':sid,'prompt_preview':text},ensure_ascii=False) for sid,text in [('a','修改申报书并同步预算附表'),('b','写一个视频'),('a','继续'),('a','那你不要停啊')]))
            with patch.object(guidance_entry,'PROMPT_INGRESS',path):
                task=build_request({'session_id':'a'},'继续','x')['task']
            self.assertIn('预算附表',task['context_summary'])
            self.assertNotIn('视频',task['context_summary'])

    def test_reference_to_previous_recommendation_is_a_continuation(self):
        request=build_request({'memory_full_prompt':'前一项活动任务：升级记忆系统目录。'},'按你建议的执行！','entry:ref')
        self.assertTrue(request['task']['continuation'])
        self.assertIn('升级记忆系统目录',request['task']['context_summary'])

    def test_renderer_keeps_selector_document_match_on_short_followup(self):
        item={'id':'doc','text':'Word 修订必须保留当前底稿','applies_when':['文档修改'],'exceptions':['新要求优先']}
        _,body=guidance_entry.render_entry({'included':[item]},'继续')
        self.assertEqual(body['included'],[item])

    def test_empty_guidance_still_provides_complete_manual(self):
        from memory_usage_instructions import CORE_TEXT
        value = guidance_entry.format_context({"included": [], "coverage": "complete_active_set"})
        self.assertIn(CORE_TEXT, value)
        self.assertLess(value.index(CORE_TEXT), value.index("evolving_profile_guidance_entry"))

    def test_manual_preserves_ambiguous_scope_and_partial_coverage_boundaries(self):
        import importlib.util
        source=Path(__file__).resolve().parents[1]/'guidance'/'memory_usage_instructions.py'
        spec=importlib.util.spec_from_file_location('source_memory_usage_instructions',source)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        CORE_TEXT=module.CORE_TEXT
        self.assertIn('先保持多个对象假设',CORE_TEXT)
        self.assertIn('不能把候选中的名称、金额拆分、阶段或关系预写进Recall/Research查询',CORE_TEXT)
        self.assertIn('找到某一版本只证明该版存在',CORE_TEXT)
        self.assertIn('不因next_offset存在就机械读完所有候选',CORE_TEXT)
        self.assertIn('机构和项目名称应逐字沿用同一来源的标准写法',CORE_TEXT)

    def test_renderer_separates_stable_profile_from_candidates(self):
        stable={'id':'stable','text':'当前要求优先','applies_when':['所有任务']}
        candidate={'id':'candidate','text':'PPT逐页检查','applies_when':['制作PPT']}
        context,body=guidance_entry.render_entry({'stable_profile':[stable],'included':[candidate],'coverage':'complete_active_set'},'制作PPT')
        self.assertEqual([row['id'] for row in body['stable_profile']],['stable'])
        self.assertEqual([row['id'] for row in body['preference_candidates']],['candidate'])
        self.assertIn('稳定协作骨架',context)
        self.assertIn('候选偏好',context)

    def test_repository_failure_preserves_manual_and_records_its_version(self):
        from memory_usage_instructions import CORE_TEXT, VERSION, content_sha256
        with tempfile.TemporaryDirectory() as root, patch.object(guidance_entry, 'RECEIPT_ROOT', Path(root)), patch.object(guidance_entry, '_call_preference', side_effect=OSError('offline')):
            entry = guidance_entry.run_entry_check({'session_id': 'test'}, '解释机制')
        self.assertIn(CORE_TEXT, entry['context'])
        self.assertEqual(entry['receipt']['instruction']['instruction_version'], VERSION)
        self.assertEqual(entry['receipt']['instruction']['content_sha256'], content_sha256())
        self.assertEqual(entry['receipt']['instruction']['model_context_visibility'], 'not_measured')

    def test_entry_records_task_state_as_separate_context_lane(self):
        with tempfile.TemporaryDirectory() as root, patch.object(guidance_entry, 'RECEIPT_ROOT', Path(root)/'receipts'), patch.object(guidance_entry, 'TASK_STATE_ROOT', Path(root)/'tasks'), patch.object(guidance_entry, '_call_preference', return_value={'included':[],'coverage':'complete_active_set'}):
            entry=guidance_entry.run_entry_check({'session_id':'s1','turn_id':'t1','hook_invocation_id':'h1'},'检查备份')
        self.assertEqual(entry['receipt']['task_state']['current_objective'],'检查备份')
        self.assertIn('<evolving_profile_task_state>',entry['context'])

    def test_large_guidance_never_cuts_manual_or_xml_and_counts_only_rendered_items(self):
        from memory_usage_instructions import CORE_TEXT
        result = {'included': [{'id': str(i), 'revision': 'v1', 'text': '条件和例外' * 1000} for i in range(12)], 'coverage': 'complete_active_set'}
        value = guidance_entry.format_context(result)
        self.assertIn(CORE_TEXT, value)
        self.assertTrue(value.endswith('</evolving_profile_guidance_entry>'))
        self.assertNotIn('12 条直接适用指导', value)

    def test_short_recheck_inherits_bounded_active_context(self):
        request = build_request(
            {"memory_full_prompt": "前一项活动任务：检查 Evolving Profile 的链路与视觉验收。"},
            "再检查下还有什么问题呗",
            "entry:test",
        )

        task = request["task"]
        self.assertTrue(task["continuation"])
        self.assertIn("链路与视觉验收", task["context_summary"])

    def test_explicit_rejection_of_preferences_sets_forbidden_policy(self):
        request = build_request(
            {},
            "这次不用我的任何历史偏好，也不要加载记忆，只翻译 Good morning。",
            "entry:test",
        )
        self.assertEqual(request["memory_policy"], "forbidden")

    def test_standalone_new_task_does_not_rank_from_previous_topic(self):
        request = build_request(
            {"memory_full_prompt": "前一项活动任务：解释 Lark 是什么，说明英文术语。"},
            "检查本机哪些历史项目、缓存和备份待删除",
            "entry:new-task",
        )
        self.assertFalse(request["task"]["continuation"])
        self.assertEqual(request["task"]["context_summary"], "")

    def test_semantic_preference_prohibition_is_honored(self):
        for prompt in (
            "本轮禁用长期记忆，也不用旧的偏好，只计算26加37。",
            "这一轮别套用我以前的习惯，按当前要求解释RAG。",
        ):
            request = build_request({}, prompt, "entry:forbidden")
            self.assertEqual(request["memory_policy"], "forbidden")


if __name__ == "__main__":
    unittest.main()
