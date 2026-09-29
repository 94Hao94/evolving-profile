import unittest

from lib.scope_hypotheses import search_contexts, build_hypotheses


def index():
    return {
        'schema': 'evolving-profile.context-index.v1', 'status': 'ready',
        'sessions': [
            {'context_id': 'session:business-50', 'context_type': 'session', 'session_id': 'business-50',
             'title': '天津财经大学商学院人工智能实训平台申报',
             'summary': {'compact': '50万元生成式人工智能实训平台，服务各系学生。'},
             'status': 'model_reviewed', 'updated_at': '2026-09-04T00:00:00Z', 'source_ids': ['s50']},
            {'context_id': 'session:yin-30', 'context_type': 'session', 'session_id': 'yin-30',
             'title': '商务智能与数据分析产教融合实践平台',
             'summary': {'compact': '天津财经大学管理科学与工程学院，30万元课程与企业项目。'},
             'status': 'model_reviewed', 'updated_at': '2026-09-17T00:00:00Z', 'source_ids': ['s30']},
            {'context_id': 'session:other', 'context_type': 'session', 'session_id': 'other',
             'title': '天津财经大学商学院校园文化项目',
             'summary': {'compact': '学生文化活动方案。'}, 'status': 'model_reviewed', 'source_ids': ['sother']},
            {'context_id': 'session:procurement', 'context_type': 'session', 'session_id': 'procurement',
             'title': '天津开发建设类服务采购文件回溯与打包完成',
             'summary': {'compact': '数据服务采购，预算30万元。'}, 'status': 'model_reviewed', 'source_ids': ['sproc']},
        ],
        'projects': []
    }


class ScopeHypothesisTest(unittest.TestCase):
    def test_same_institution_returns_separate_context_candidates(self):
        rows = search_contexts(index(), '天津财经大学 商务智能与数据分析 30万元', limit=10)
        ids = [row['scenario_id'] for row in rows['items']]
        self.assertIn('session:yin-30', ids)
        background_ids = [row['scenario_id'] for row in rows['background_items']]
        self.assertIn('session:business-50', background_ids)
        self.assertNotIn('session:business-50', ids)
        self.assertEqual(rows['source'], 'scenario_context_index')
        self.assertTrue(all('summary' not in row for row in rows['items']))
        self.assertTrue(rows['coverage']['navigation_only'])

    def test_background_institution_match_does_not_create_competing_hypothesis(self):
        rows = search_contexts(index(), '天津财经大学 商务智能与数据分析 30万元', limit=10)
        result = build_hypotheses('天津财经大学 商务智能与数据分析 30万元', rows['items'])
        background_ids = [item['scenario_id'] for item in rows['background_items']]
        self.assertIn('session:business-50', background_ids)
        self.assertIn('session:other', background_ids)
        self.assertEqual([item['scenario_ids'][0] for item in result['hypotheses']], ['session:yin-30'])

    def test_amount_and_generic_word_cannot_promote_unrelated_session(self):
        rows = search_contexts(index(), '天津财经大学 商务智能与数据分析 30万元', limit=10)
        main_ids = [row['scenario_id'] for row in rows['items']]
        background_ids = [row['scenario_id'] for row in rows['background_items']]
        self.assertIn('session:yin-30', main_ids)
        self.assertNotIn('session:procurement', main_ids)
        self.assertIn('session:procurement', background_ids)

    def test_catalog_miss_is_unknown_not_empty_bank_claim(self):
        rows = search_contexts(index(), '天津财经大学 具身智能', limit=10)
        self.assertEqual(rows['items'], [])
        self.assertEqual(rows['coverage']['status'], 'not_found_in_context_index')
        self.assertEqual(rows['coverage']['bank_absence'], 'unknown')

    def test_hypotheses_preserve_competing_projects_and_abstain(self):
        rows = search_contexts(index(), '天津财经大学 平台', limit=10)
        result = build_hypotheses('天津财经大学 平台', rows['items'])
        self.assertGreaterEqual(len(result['hypotheses']), 2)
        self.assertEqual(result['decision'], 'agent_decides')
        self.assertIn('ambiguous', {item['status'] for item in result['hypotheses']})
        self.assertTrue(all(item['accepted_as_fact'] is False for item in result['hypotheses']))

    def test_project_directory_does_not_promote_unverified_workspace_bucket(self):
        payload = index();payload['projects']=[{'context_id':'project:cwd','context_type':'project','project_key':'cwd',
            'title':'天津财经大学管理科学与工程学院','identity_status':'unverified_workspace_bucket',
            'summary':{'compact':'30万元商务智能项目'}}]
        rows = search_contexts(payload, '天津财经大学 商务智能', context_type='project', limit=10)
        self.assertEqual(rows['items'], [])
        self.assertEqual(rows['coverage']['excluded_unverified_projects'], 1)

    def test_missing_title_uses_only_a_bounded_navigation_heading(self):
        payload = index();payload['sessions'][1].pop('title')
        rows = search_contexts(payload, '天津财经大学 30万元', limit=10)
        row = next(item for item in rows['items'] if item['scenario_id'] == 'session:yin-30')
        self.assertEqual(row['navigation_title'], '')

    def test_navigation_roles_prioritize_without_promoting_fact(self):
        rows = search_contexts(index(), '天津财经大学 商务智能与数据分析 30万元', limit=10)
        self.assertIn(rows['items'][0]['navigation_role'], {'primary_candidate', 'competing_candidate'})
        self.assertTrue(all(item['navigation_only'] for item in rows['items']))
        self.assertTrue(all(item['navigation_role'] != 'accepted_fact' for item in rows['items']))


if __name__ == '__main__':
    unittest.main()
