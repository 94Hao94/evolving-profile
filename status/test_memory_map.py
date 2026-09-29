import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


class MemoryMapTest(unittest.TestCase):
    def test_candidate_audit_page_is_bound_and_complete_not_live_reconstruction(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as root:
            research=Path(root)/'memory-os/research'
            research.mkdir(parents=True)
            (research/'rid.json').write_text(json.dumps({'query':'query','memory_ids':[str(i) for i in range(36)],
                'candidate_audit':[{'id':str(i),'text':'snapshot '+str(i),'delivery':'not_returned'} for i in range(36)],
                'delivery_events':[{'check_id':'prompt-a','delivered_items':[{'id':'22','text':'actual delivered excerpt'}]},
                                   {'check_id':'prompt-b','delivered_items':[{'id':'22','text':'foreign prompt body'},
                                                                         {'id':'23','text':'later body'}]}]}))
            row={'hook_invocation_id':'prompt-a','memory_route_receipt':{'tool_events':[{'tool':'recall','research_id':'rid'}]}}
            with patch.object(self.module,'STATE_ROOT',Path(root)):
                result=self.module.candidate_audit_page(row,'rid',20,10)
                foreign=self.module.candidate_audit_page(row,'other',0,10)
        self.assertEqual(result['total'],36)
        self.assertEqual(result['next_offset'],30)
        self.assertEqual(result['items'][2]['delivered_text'],'actual delivered excerpt')
        self.assertEqual(result['items'][2]['delivery'],'text_returned')
        self.assertEqual(result['items'][3]['delivery'],'not_returned')
        self.assertEqual(foreign['snapshot_status'],'not_bound_to_prompt')

    def test_partial_later_snapshots_do_not_claim_complete_old_discovery(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as root:
            research=Path(root)/'memory-os/research';research.mkdir(parents=True)
            (research/'rid.json').write_text(json.dumps({'memory_ids':['a','b'],
                'candidate_audit':[{'id':'a','text':'later body','snapshot_stage':'source_read'}]}))
            row={'memory_route_receipt':{'tool_events':[{'tool':'recall','research_id':'rid'}]}}
            with patch.object(self.module,'STATE_ROOT',Path(root)):
                result=self.module.candidate_audit_page(row,'rid',0,10)
        self.assertEqual(result['total'],2)
        self.assertEqual(result['snapshot_status'],'partial_history')
        self.assertEqual(result['missing_discovery_snapshot_count'],2)
        self.assertEqual(result['items'][1]['reason'],'historical_snapshot_missing')

    def test_fallback_bound_events_are_candidate_groups(self):
        row={'time_window_activity':{'boundary':'same_prompt_binding_only','events':[
            {'tool':'recall','research_id':'rid','candidate_count':36}]}}
        groups=self.module.candidate_groups_for_prompt(row)
        self.assertEqual(groups,[{'id':'rid','actor':'agent_mcp','count':36}])

    def test_old_probe_count_without_snapshot_is_unknown_not_fabricated(self):
        row={'system_probe':{'candidate_count':6,'items':[]}}
        result=self.module.candidate_audit_page(row,'system_probe',0,10)
        self.assertEqual(result['total'],6)
        self.assertEqual(result['items'],[])
        self.assertEqual(result['snapshot_status'],'historical_snapshot_missing')

    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('memory_map_status_test', Path(__file__).with_name('evolving_profile_status_server.py'))
        cls.module=importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.module)

    def test_map_keeps_catalog_layers_separate_from_evidence(self):
        value=self.module.memory_map_snapshot()
        self.assertEqual([x['id'] for x in value['layers']], ['L0','L1','L2'])
        self.assertTrue(all('route' in node and 'summary' in node for node in value['nodes']))
        self.assertEqual(value['route_policy']['current_prompt_first'], True)

    def test_map_reports_knowledge_pages_and_navigation_topics_separately(self):
        class Catalog:
            def __init__(self,_path):pass
            def list(self,limit):return [{'topic_id':'manifest:a'},{'topic_id':'entity:b'}]
            def count(self):return 2
        original_catalog=self.module.TopicCatalog;original_get=self.module.get
        self.module.TopicCatalog=Catalog
        self.module.get=lambda _base,path,*_args:{'roots':[{'id':'kp-1'}]} if path.endswith('/knowledge-base/tree') else {}
        try:value=self.module.memory_map_snapshot()['topic_catalog']
        finally:self.module.TopicCatalog=original_catalog;self.module.get=original_get
        self.assertEqual(value['knowledge_page_count'],1)
        self.assertEqual(value['navigation_topic_count'],2)
        self.assertEqual(value['topic_count'],3)

    def test_map_exposes_live_fact_counts_when_stats_available(self):
        original=self.module.get
        self.module.get=lambda *_args,**_kwargs: {'nodes_by_fact_type': {'world': 2, 'experience': 3, 'observation': 4}, 'links_by_link_type': {'entity': 5}}
        try:
            nodes={node['id']:node for node in self.module.memory_map_snapshot()['nodes']}
        finally:
            self.module.get=original
        self.assertEqual(nodes['world']['count'],2)
        self.assertEqual(nodes['entities']['count'],5)

    def test_route_probe_escalates_complex_history(self):
        value=self.module.memory_check('请回顾之前项目的时间线、实体冲突和原始来源')
        self.assertEqual(value['recommended_route'], 'research')
        self.assertIn('entities', value['matched_nodes'])
        self.assertIn('sources', value['matched_nodes'])
        self.assertTrue(value['requires_receipt'])

    def test_time_window_separates_exact_and_unattributed_tool_activity(self):
        prompt_at = '2026-09-20T10:00:00+00:00'
        current = {
            'check_id': 'prompt-a',
            'prompt_binding': {'session_id':'session-a','turn_id':'turn-a','hook_invocation_id':'prompt-a'},
            'tool_events': [
                {'tool':'mcp__evolving_profile_controller__recall','at':'2026-09-20T10:01:00+00:00',
                 'check_id':'prompt-a','session_id':'session-a','turn_id':'turn-a','returned_count':3},
            ],
        }
        other = {
            'check_id': 'prompt-b',
            'prompt_binding': {'session_id':'session-b','turn_id':'turn-b','hook_invocation_id':'prompt-b'},
            'tool_events': [
                {'tool':'mcp__evolving_profile_controller__research','at':'2026-09-20T10:01:30+00:00',
                 'check_id':'prompt-b','session_id':'session-b','turn_id':'turn-b','returned_count':6,
                 'memory_ids':['must-not-leak-under-current-prompt']},
            ],
        }
        global_activity = [
            {'tool':'mcp__evolving_profile_controller__recall','at':'2026-09-20T10:01:30+00:00',
             'check_id':'prompt-b','session_id':'session-b','turn_id':'turn-b','returned_count':6,
             'memory_ids':['must-not-leak-under-current-prompt']},
            {'tool':'mcp__evolving_profile_controller__research','at':'2026-09-20T10:01:45+00:00',
             'check_id':'','returned_count':4,'memory_ids':['unbound-content']},
        ]
        value = self.module._time_window_tool_activity(
            prompt_at, [current,other], window_minutes=2, global_activity=global_activity)
        self.assertEqual(value['event_count'],1)
        self.assertEqual(value['by_tool']['recall']['returned'],3)
        self.assertEqual(value['events'][0]['check_id'],'prompt-a')
        self.assertEqual(value['unattributed_activity']['event_count'],2)
        self.assertEqual(value['unattributed_activity']['by_tool']['recall']['calls'],1)
        self.assertEqual(value['unattributed_activity']['by_tool']['research']['calls'],1)
        self.assertNotIn('events',value['unattributed_activity'])
        self.assertNotIn('memory_ids',value['unattributed_activity'])
        self.assertEqual(value['boundary'],'same_prompt_binding_only')

    def test_default_prompt_tool_observation_window_is_two_minutes(self):
        value = self.module._time_window_tool_activity(
            '2026-09-20T10:00:00+00:00',
            [{'check_id':'prompt-a','prompt_binding':{'session_id':'s','turn_id':'t','hook_invocation_id':'prompt-a'},'tool_events':[]}],
            global_activity=[
                {'tool': 'mcp__evolving_profile_controller__recall', 'at': '2026-09-20T10:01:59+00:00', 'check_id':'prompt-a','returned_count': 1},
                {'tool': 'mcp__evolving_profile_controller__research', 'at': '2026-09-20T10:02:01+00:00', 'check_id':'prompt-a','returned_count': 2},
            ],
        )
        self.assertEqual(value['window_minutes'], 2)
        self.assertEqual(value['event_count'], 1)

    def test_default_prompt_guidance_observation_window_is_two_minutes(self):
        value = self.module._time_window_guidance_activity(
            '2026-09-20T10:00:00+00:00',
            [{'at': '2026-09-20T10:01:59+00:00','session_id':'s','turn_id':'t','hook_invocation_id':'prompt-a','entry_context_included_count': 2}],
            [],prompt_binding={'session_id':'s','turn_id':'t','hook_invocation_id':'prompt-a'},
        )
        self.assertEqual(value['window_minutes'], 2)
        self.assertEqual(value['event_count'], 1)

    def test_guidance_time_window_separates_other_threads_and_unbound_calls(self):
        value=self.module._time_window_guidance_activity(
            '2026-09-20T10:00:00+00:00',
            [{'at':'2026-09-20T10:00:30+00:00','session_id':'session-a','turn_id':'turn-a',
              'hook_invocation_id':'prompt-a','entry_context_included_count':2}],
            [],window_minutes=2,global_activity=[
                {'tool':'mcp__evolving_profile_controller__get_task_guidance','at':'2026-09-20T10:00:45+00:00',
                 'session_id':'session-b','turn_id':'turn-b','check_id':'prompt-b','guidance_count':3,'guidance_ids':['other-thread']},
                {'tool':'mcp__evolving_profile_controller__get_task_guidance','at':'2026-09-20T10:00:50+00:00',
                 'check_id':'','guidance_count':4,'guidance_ids':['unbound-content']},
            ],prompt_binding={'session_id':'session-a','turn_id':'turn-a','hook_invocation_id':'prompt-a'},
            prompt_ingress=[{'at':'2026-09-20T10:00:00+00:00','session_id':'session-a','turn_id':'turn-a','hook_invocation_id':'prompt-a'}])
        self.assertEqual(value['event_count'],1)
        self.assertEqual(value['returned_count'],2)
        self.assertEqual(value['unattributed_activity']['event_count'],2)
        self.assertNotIn('ids',value['unattributed_activity'])

    def test_time_window_activity_counts_read_source_and_find_sources(self):
        value = self.module._time_window_tool_activity(
            '2026-09-20T10:00:00+00:00',
            [{'check_id':'prompt-a','prompt_binding':{'session_id':'s','turn_id':'t','hook_invocation_id':'prompt-a'},'tool_events':[]}],
            global_activity=[
                {'tool': 'mcp__evolving_profile_controller__read_source', 'at': '2026-09-20T10:01:30+00:00', 'check_id':'prompt-a', 'returned_count': 1, 'memory_id': 'm1'},
                {'tool': 'mcp__evolving_profile_controller__find_sources', 'at': '2026-09-20T10:01:45+00:00', 'check_id':'prompt-a', 'returned_count': 2},
            ],
            window_minutes=2,
        )
        self.assertEqual(value['by_tool']['read_source']['calls'], 1)
        self.assertEqual(value['by_tool']['find_sources']['returned'], 2)

    def test_scenario_tool_observation_keeps_bound_ids_and_hides_unattributed_ids(self):
        value = self.module._time_window_tool_activity(
            '2026-09-20T10:00:00+00:00',
            [{'prompt_binding': {'session_id': 's', 'turn_id': 't', 'hook_invocation_id': 'prompt-a'},
              'tool_events': [{'tool': 'read_scenario_summary', 'at': '2026-09-20T10:00:30+00:00',
                               'check_id': 'prompt-a', 'session_id': 's', 'turn_id': 't',
                               'returned_count': 1, 'scenario_ids': ['session:s1']}]}],
            global_activity=[{'tool': 'read_scenario_summary', 'at': '2026-09-20T10:00:45+00:00',
                              'check_id': '', 'returned_count': 1, 'scenario_ids': ['private-other']}],
            prompt_binding={'session_id': 's', 'turn_id': 't', 'hook_invocation_id': 'prompt-a'},
        )
        self.assertEqual(value['by_tool']['read_scenario_summary']['calls'], 1)
        self.assertEqual(value['events'][0]['scenario_ids'], ['session:s1'])
        self.assertEqual(value['unattributed_activity']['event_count'], 1)
        self.assertNotIn('scenario_ids', value['unattributed_activity'])

    def test_hydrates_recall_candidates_separately_when_zero_items_returned(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            root = Path(directory)
            research = root / 'memory-os' / 'research'
            research.mkdir(parents=True)
            (research / 'research-1.json').write_text(json.dumps({
                'research_id': 'research-1',
                'status': 'discovered_not_verified',
                'memory_ids': ['candidate-1', 'candidate-2'],
            }), encoding='utf-8')
            original_root = self.module.STATE_ROOT
            original_get = self.module.get
            self.module.STATE_ROOT = root
            self.module.get = lambda _base, path, *_args: {
                'id': path.rsplit('/', 1)[-1],
                'type': 'experience',
                'state': 'valid',
                'text': 'candidate preview',
            }
            try:
                value = self.module._hydrate_time_window_content({
                    'state': 'observed',
                    'events': [{
                        'tool': 'recall',
                        'returned_count': 0,
                        'candidate_count': 2,
                        'research_id': 'research-1',
                    }],
                })
            finally:
                self.module.STATE_ROOT = original_root
                self.module.get = original_get
        self.assertEqual(value['items'], [])
        self.assertEqual(value['candidate_count'], 2)
        self.assertEqual([item['id'] for item in value['candidate_items']], ['candidate-1', 'candidate-2'])
        self.assertTrue(all(item['candidate_only'] for item in value['candidate_items']))

    def test_post_prompt_guidance_window_counts_returned_entries(self):
        value = self.module._time_window_guidance_activity(
            '2026-09-20T10:00:00+00:00',
            [{'at': '2026-09-20T10:03:00+00:00','session_id':'s','turn_id':'t','hook_invocation_id':'prompt-a','entry_context_included_count': 4, 'deferred_count': 2}],
            [],
            window_minutes=5,
            prompt_binding={'session_id':'s','turn_id':'t','hook_invocation_id':'prompt-a'},
        )
        self.assertEqual(value['state'], 'observed')
        self.assertEqual(value['returned_count'], 4)
        self.assertEqual(value['deferred_count'], 2)
        self.assertEqual(value['boundary'], 'same_prompt_binding_only')

    def test_catalog_entity_match_turns_an_implicit_topic_into_recall(self):
        original=self.module._catalog_probe
        self.module._catalog_probe=lambda _prompt: {'status':'observed','candidate_count':3,'matched_entities':['Evolving Profile'],'entity_count':1}
        try:
            value=self.module.memory_check('Evolving Profile 2.0 PRD')
        finally:
            self.module._catalog_probe=original
        self.assertEqual(value['recommended_route'],'recall')
        self.assertEqual(value['history_dependency'],'possible')
        self.assertEqual(value['catalog_probe']['candidate_count'],3)

    def test_explicit_no_history_skips_without_probing_bank(self):
        original=self.module._catalog_probe
        called=[]
        self.module._catalog_probe=lambda prompt: called.append(prompt) or {'status':'observed','candidate_count':9,'matched_entities':['Bank'],'entity_count':1}
        try:
            value=self.module.memory_check('不要调用历史记忆，也不用 recall 或 research，只计算 2+2。')
        finally:
            self.module._catalog_probe=original
        self.assertEqual(value['recommended_route'],'skip')
        self.assertEqual(value['catalog_probe']['status'],'forbidden')
        self.assertEqual(value['suggested_tools'],[])
        self.assertEqual(called,[])

    def test_forbidden_route_does_not_read_map_stats_or_catalog(self):
        original_map=self.module.memory_map_snapshot
        original_probe=self.module._catalog_probe
        self.module.memory_map_snapshot=lambda: (_ for _ in ()).throw(AssertionError('memory map read'))
        self.module._catalog_probe=lambda _prompt: (_ for _ in ()).throw(AssertionError('catalog read'))
        try:
            value=self.module.memory_check('本次不使用个人记忆，只根据下面材料回答。')
        finally:
            self.module.memory_map_snapshot=original_map
            self.module._catalog_probe=original_probe
        self.assertEqual(value['recommended_route'],'skip')
        self.assertEqual(value['catalog_probe']['status'],'forbidden')

    def test_current_material_does_not_hide_explicit_historical_comparison(self):
        original=self.module._catalog_probe
        self.module._catalog_probe=lambda _prompt:{'status':'catalog_observed','candidate_count':2,'matched_entities':['项目决策'],'entity_count':1,'hints':[]}
        try:value=self.module.memory_check('帮我对比当前材料与上次项目的决策。')
        finally:self.module._catalog_probe=original
        self.assertEqual(value['recommended_route'],'recall')
        self.assertEqual(value['catalog_probe']['status'],'catalog_observed')

    def test_explanation_negation_does_not_hide_historical_request(self):
        original=self.module._catalog_probe
        self.module._catalog_probe=lambda _prompt:{'status':'catalog_observed','candidate_count':1,'matched_entities':['最终决定'],'entity_count':1,'hints':[]}
        try:value=self.module.memory_check('不需要科普技术原理，请回顾上周我们作出的最终决定。')
        finally:self.module._catalog_probe=original
        self.assertEqual(value['recommended_route'],'recall')

    def test_equivalent_memory_prohibitions_skip_before_bank_probe(self):
        original=self.module._catalog_probe
        called=[]
        self.module._catalog_probe=lambda prompt: called.append(prompt) or {'status':'observed','candidate_count':9,'matched_entities':[],'entity_count':1}
        try:
            prompts=('本轮禁用长期记忆，只回答这次给出的材料。','不要参考之前的聊天记录，今天只按这份清单检查。','关闭本轮历史检索，仅润色下面的短句：进度已同步。')
            values=[self.module.memory_check(prompt) for prompt in prompts]
        finally:self.module._catalog_probe=original
        self.assertTrue(all(value['recommended_route']=='skip' for value in values))
        self.assertTrue(all(value['catalog_probe']['status']=='forbidden' for value in values))
        self.assertEqual(called,[])

    def test_preference_only_prohibition_keeps_historical_fact_route_available(self):
        original=self.module._catalog_probe
        called=[]
        self.module._catalog_probe=lambda prompt: called.append(prompt) or {'status':'catalog_observed','candidate_count':2,'matched_entities':['备份'],'entity_count':1,'hints':[]}
        try:value=self.module.memory_check('不要使用我的偏好，请回顾上次备份最后是否成功。')
        finally:self.module._catalog_probe=original
        self.assertEqual(value['recommended_route'],'recall')
        self.assertEqual(value['catalog_probe']['status'],'catalog_observed')
        self.assertIn('recall',value['suggested_tools'])
        self.assertEqual(called,['不要使用我的偏好，请回顾上次备份最后是否成功。'])

    def test_historical_paraphrases_are_consistent(self):
        original=self.module._catalog_probe
        self.module._catalog_probe=lambda _prompt: {'status':'observed','candidate_count':4,'matched_entities':[],'entity_count':2,'hints':[]}
        try:
            prompts=('我以前要求报告用哪种排版格式？','上回那个报销字段解锁之后，最后恢复限制了吗？','咱们已经拍板的云备份安排怎么定的？')
            values=[self.module.memory_check(prompt) for prompt in prompts]
        finally:self.module._catalog_probe=original
        self.assertTrue(all(value['recommended_route'] in {'recall','research'} for value in values))

    def test_quoted_history_word_and_live_command_are_self_contained(self):
        original=self.module._catalog_probe
        called=[]
        self.module._catalog_probe=lambda prompt: called.append(prompt) or {'status':'observed','candidate_count':4,'matched_entities':[],'entity_count':2}
        try:
            translation=self.module.memory_check("把‘之前没有备份’译成英文。")
            live=self.module.memory_check('查一下电脑上 Python 的版本，以命令运行结果为准。')
        finally:self.module._catalog_probe=original
        self.assertEqual(translation['recommended_route'],'skip')
        self.assertEqual(live['recommended_route'],'skip')
        self.assertEqual(called,[])

    def test_supplied_text_language_edits_ignore_historical_words_in_the_material(self):
        original=self.module._catalog_probe;called=[]
        self.module._catalog_probe=lambda prompt:called.append(prompt) or {}
        try:
            values=[self.module.memory_check(prompt) for prompt in (
                "以下段落提到‘过去版本’，请只做病句修改。",
                "把下面文字中的历史项目改成旧项目，只润色这段文字。",
            )]
        finally:self.module._catalog_probe=original
        self.assertTrue(all(value['recommended_route']=='skip' for value in values))
        self.assertEqual(called,[])

    def test_explicit_live_local_tool_queries_skip_personal_history(self):
        original=self.module._catalog_probe;called=[]
        self.module._catalog_probe=lambda prompt:called.append(prompt) or {}
        try:
            values=[self.module.memory_check(prompt) for prompt in (
                "查看此刻本机磁盘还剩多少，以系统命令为准。",
                "用终端读取当前这台电脑的 Python 版本。",
            )]
        finally:self.module._catalog_probe=original
        self.assertTrue(all(value['recommended_route']=='skip' for value in values))
        self.assertEqual(called,[])

    def test_current_context_conflict_does_not_become_historical_research(self):
        original=self.module._catalog_probe
        self.module._catalog_probe=lambda _prompt: {'status':'skipped','candidate_count':None,'matched_entities':[],'entity_count':0}
        try:
            value=self.module.memory_check('下面两条需求有冲突吗：最多100字；必须写200字。')
        finally:
            self.module._catalog_probe=original
        self.assertEqual(value['recommended_route'],'skip')

    def test_supplied_text_edit_does_not_become_source_read(self):
        original=self.module._catalog_probe
        self.module._catalog_probe=lambda _prompt: {'status':'skipped','candidate_count':None,'matched_entities':[],'entity_count':0}
        try:
            value=self.module.memory_check('把这句话里的版本改成版次：这是第二个版本。')
        finally:
            self.module._catalog_probe=original
        self.assertEqual(value['recommended_route'],'skip')

    def test_short_chinese_entity_can_route_an_implicit_historical_question(self):
        original=self.module._catalog_probe
        self.module._catalog_probe=lambda _prompt: {'status':'observed','candidate_count':5,'matched_entities':['小黛'],'entity_count':4,'hints':[{'memory_id':'m1','title':'小黛回复故障'}]}
        try:
            value=self.module.memory_check('小黛空回复的问题后来怎么处理的？')
        finally:
            self.module._catalog_probe=original
        self.assertEqual(value['recommended_route'],'recall')
        self.assertEqual(value['catalog_hints'][0]['memory_id'],'m1')

    def test_live_terminal_state_is_not_routed_to_archived_source(self):
        original=self.module._catalog_probe
        self.module._catalog_probe=lambda _prompt: {'status':'skipped','candidate_count':None,'matched_entities':[],'entity_count':0}
        try:
            value=self.module.memory_check('检查本机现在安装的 Node 版本，用终端查就好。')
        finally:
            self.module._catalog_probe=original
        self.assertEqual(value['recommended_route'],'skip')

    def test_catalog_hints_do_not_copy_fact_bodies(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*_args):return False
            def read(self):return json.dumps({'results':[{'id':'m1','type':'experience','text':'SECRET FACT BODY','document_id':'d1'}],'entities':{'小黛':{'canonical_name':'小黛'}}}).encode()
        import tempfile
        with tempfile.TemporaryDirectory() as root, patch.object(self.module,'TOPIC_CATALOG_PATH',Path(root)/'empty.sqlite3'), patch.object(self.module.urllib.request,'urlopen',return_value=Response()):
            value=self.module._catalog_probe('小黛怎么处理的？')
        self.assertEqual(value['status'],'catalog_miss')
        self.assertNotIn('SECRET FACT BODY',json.dumps(value,ensure_ascii=False))
        self.assertEqual(value['hints'],[])

if __name__=='__main__': unittest.main()
