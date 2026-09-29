import tempfile
import unittest
from pathlib import Path

from topic_catalog import TopicCatalog,redact_unreviewed_page,merge_catalog_rows


class TopicCatalogTest(unittest.TestCase):
    def test_broad_domain_is_not_hidden_by_popular_incidental_entity_names(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=TopicCatalog(Path(root)/'topics.sqlite3')
            catalog.replace_topics([{'topic_id':'domain:health','title':'个人健康与生活','level':'L0','overview':'医疗咨询和健康记录'}],entity_index=[
                {'id':'entity:check','title':'健康检查','source_count':900}, {'id':'entity:light','title':'健康照明','source_count':700}])
            self.assertEqual(catalog.search('健康',2)[0]['topic_id'],'domain:health')

    def test_source_membership_paginates_and_replacement_removes_deleted_sources(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=TopicCatalog(Path(root)/'topics.sqlite3')
            leaf={'topic_id':'topic:rare','title':'低频历史','level':'L1','parent_id':'domain:life','memory_count':3,'children':[]}
            members=[['m1','d1','topic:rare','r1'],['m2','d2','topic:rare','r2'],['m3','d2','topic:rare','r3']]
            catalog.replace_topics([leaf],members=members)
            first=catalog.evidence_page('topic:rare',0,2)
            self.assertEqual(first['total'],3)
            self.assertEqual(first['next_offset'],2)
            self.assertEqual(catalog.get('topic:rare')['parent_id'],'domain:life')
            self.assertEqual(catalog.evidence_page('topic:rare',2,2)['items'][0]['memory_id'],'m3')
            catalog.replace_topics([leaf],members=members[:1])
            self.assertEqual(catalog.evidence_page('topic:rare')['total'],1)

    def test_long_tail_entity_is_searchable_outside_preview_limit(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=TopicCatalog(Path(root)/'topics.sqlite3')
            catalog.replace_topics([{'topic_id':'manifest:core','title':'核心主题'}], metadata={'revision':'r1'}, entity_index=[
                {'id':'entity:rare','title':'罕见项目决策','source_count':1,'latest_source_at':'2026-09-20'},
            ])
            result=catalog.search('罕见项目',limit=3)
            self.assertEqual(result[0]['topic_id'],'entity:rare')
            self.assertEqual(catalog.get('entity:rare')['title'],'罕见项目决策')
            self.assertEqual(catalog.index_count(),1)

    def test_topic_keeps_sources_freshness_and_conflicts(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=TopicCatalog(Path(root)/'topics.sqlite3')
            catalog.replace_topics([{
                'topic_id':'entity:backup','title':'备份','abstract':'备份策略、清理与恢复验证',
                'overview':'覆盖本地备份、云镜像、空间清理与恢复验证。',
                'entities':['备份','WPS'],'time_range':{'start':'2026-07-01','end':'2026-09-19'},
                'source_count':4,'source_locators':[{'memory_id':'m1','document_id':'d1'}],
                'coverage':{'sampled':4,'total':5},'pending_changes':1,
                'conflicts':['云同步状态存在版本差异'],'children':[],'refreshed_at':'2026-09-19T00:00:00Z'
            }])
            row=catalog.get('entity:backup')
        self.assertEqual(row['source_locators'][0]['memory_id'],'m1')
        self.assertEqual(row['pending_changes'],1)
        self.assertEqual(row['coverage']['total'],5)
        self.assertTrue(row['conflicts'])

    def test_search_uses_title_entities_and_overview(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=TopicCatalog(Path(root)/'topics.sqlite3')
            catalog.replace_topics([
                {'topic_id':'entity:backup','title':'备份','abstract':'本地和云备份','overview':'恢复验证与空间清理','entities':['WPS'],'source_count':3},
                {'topic_id':'entity:trainer','title':'Trainer','abstract':'复习训练','overview':'固定页脚与复习队列','entities':['Trainer'],'source_count':2},
            ])
            self.assertEqual(catalog.search('云镜像备份')[0]['topic_id'],'entity:backup')
            self.assertEqual(catalog.search('固定页脚')[0]['topic_id'],'entity:trainer')

    def test_explicit_entity_anchor_beats_incidental_overview_overlap(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=TopicCatalog(Path(root)/'topics.sqlite3')
            catalog.replace_topics([
                {'topic_id':'entity:backup','title':'备份','abstract':'备份策略','overview':'空间清理','source_count':3},
                {'topic_id':'entity:chat','title':'微信','abstract':'微信资料','overview':'提到云镜像备份和其他内容','source_count':20},
            ])
            self.assertEqual(catalog.search('备份 云镜像')[0]['topic_id'],'entity:backup')

    def test_markdown_projection_is_navigation_not_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=TopicCatalog(Path(root)/'topics.sqlite3')
            catalog.replace_topics([{'topic_id':'entity:x','title':'X','abstract':'主题摘要','overview':'主题概览','source_count':1}])
            output=catalog.project_markdown(Path(root)/'markdown')
            text=output[0].read_text()
        self.assertIn('navigation_only',text)
        self.assertIn('主题概览',text)

    def test_markdown_projection_uses_stable_ids_and_removes_stale_outputs(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=TopicCatalog(Path(root)/'topics.sqlite3');output_root=Path(root)/'markdown'
            catalog.replace_topics([
                {'topic_id':'entity:first','title':'同名主题','source_count':1},
                {'topic_id':'entity:second','title':'同名主题','source_count':1},
            ])
            first_paths=catalog.project_markdown(output_root)
            self.assertEqual(len(first_paths),2)
            self.assertEqual(len({path.name for path in first_paths}),2)
            catalog.replace_topics([{'topic_id':'entity:second','title':'已改名主题','source_count':1}])
            second_paths=catalog.project_markdown(output_root)
            disk_paths=list(output_root.glob('*.md'))
        self.assertEqual(len(second_paths),1)
        self.assertEqual([path.name for path in disk_paths],[second_paths[0].name])

    def test_unreviewed_knowledge_page_body_is_withheld(self):
        with tempfile.TemporaryDirectory() as root:
            review=Path(root)/'review.json';review.write_text('{"pages":{"p1":{"state":"needs_review","reason":"stale claim"}}}')
            row=redact_unreviewed_page({'id':'p1','name':'Page','body':'UNVERIFIED CLAIM','markdown':'UNVERIFIED CLAIM'},review)
        self.assertNotIn('body',row);self.assertNotIn('markdown',row)
        self.assertEqual(row['content_status'],'withheld_pending_source_review')

    def test_catalog_merge_keeps_entity_fallback_and_row_sources(self):
        official=[{'id':'page-1','name':'备份页'}]
        entities=[{'topic_id':'entity:backup','title':'备份'},{'topic_id':'page-1','title':'重复项'}]
        rows=merge_catalog_rows(official,entities,limit=10)
        self.assertEqual(len(rows),2)
        self.assertEqual({row['catalog_source'] for row in rows},{'hindsight_knowledge_pages','entity_navigation_catalog'})
        self.assertEqual(sum(row.get('stable_topic_id')=='page-1' for row in rows),1)

    def test_catalog_merge_returns_entity_rows_when_official_search_is_empty(self):
        rows=merge_catalog_rows([], [{'topic_id':'entity:trainer','title':'Trainer'}], limit=8)
        self.assertEqual(rows[0]['stable_topic_id'],'entity:trainer')
        self.assertEqual(rows[0]['catalog_source'],'entity_navigation_catalog')

    def test_unknown_derived_states_are_not_normalized_to_zero(self):
        with tempfile.TemporaryDirectory() as root:
            catalog=TopicCatalog(Path(root)/'topics.sqlite3')
            catalog.replace_topics([{'topic_id':'entity:x','title':'X','source_count':4}])
            row=catalog.get('entity:x')
        self.assertIsNone(row['pending_changes'])
        self.assertIsNone(row['conflicts'])
        self.assertIsNone(row['children'])
        self.assertEqual(row['content_status'],'entity_navigation_only')


if __name__=='__main__':unittest.main()
