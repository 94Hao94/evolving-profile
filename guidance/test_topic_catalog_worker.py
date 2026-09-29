import unittest

from topic_catalog_worker import build_manifest_topics, build_topic, select_entities


class TopicCatalogWorkerTest(unittest.TestCase):
    def test_semantic_proposal_requires_real_sources_and_bounded_navigation(self):
        from topic_semantics import validate_proposals
        sources={'m1':{'id':'m1','text':'本地备份与恢复演练','document_id':'d1'},'m2':{'id':'m2','text':'云端镜像','document_id':'d2'}}
        proposed=[{'id':'backup','title':'备份','summary':'查找本地备份、云端镜像和恢复验证','questions':['怎样恢复？'],'source_ids':['m1','m2']},
                  {'id':'invented','title':'臆造','summary':'没有来源的结论','questions':[],'source_ids':['bad']}]
        result=validate_proposals(proposed,sources,limit_chars=120)
        self.assertEqual([item['id'] for item in result['accepted']],['backup'])
        self.assertEqual(result['rejected'][0]['id'],'invented')

    def test_semantic_snapshot_only_publishes_matching_source_revision(self):
        from topic_semantics import merge_semantic_snapshot
        baseline=[{'topic_id':'manifest:backup','title':'备份','navigation_summary':'人工导航','overview':'可导航问题：恢复？','source_locators':[]}]
        snapshot={'source_revision':'rev1','quality_gate':'passed','topics':[{'topic_id':'manifest:backup','title':'备份','summary':'有本地备份和恢复验证资料','questions':['怎样验证恢复？'],'source_ids':['m1']}], 'generated_at':'2026-09-20T00:00:00Z'}
        unchanged=merge_semantic_snapshot(baseline,snapshot,'rev2')
        self.assertEqual(unchanged[0]['navigation_summary'],'人工导航')
        updated=merge_semantic_snapshot(baseline,snapshot,'rev1')
        self.assertEqual(updated[0]['navigation_summary'],'有本地备份和恢复验证资料')
        self.assertEqual(updated[0]['semantic_status'],'model_generated_source_ids_checked')

    def test_dynamic_topic_keeps_source_links_and_stale_state(self):
        from topic_semantics import merge_semantic_snapshot
        snapshot={'source_revision':'r1','quality_gate':'passed','generated_at':'2026-09-20T00:00:00Z','topics':[
            {'topic_id':'dynamic:training','title':'课程训练','summary':'可查询课程训练和复习记录','questions':['如何安排复习？'],
             'source_ids':['m1','m2'],'source_locators':[{'memory_id':'m1','document_id':'d1'},{'memory_id':'m2','document_id':'d2'}],'source_documents':2}]}
        topic=merge_semantic_snapshot([],snapshot,'r1')[0]
        self.assertEqual(topic['topic_id'],'dynamic:training')
        self.assertEqual(topic['source_count'],2)
        self.assertEqual(topic['source_locators'][0]['memory_id'],'m1')
        stale=merge_semantic_snapshot([],snapshot,'r2')[0]
        self.assertEqual(stale['semantic_status'],'stale_pending_update')

    def test_unreviewed_model_output_cannot_reach_entry_map(self):
        from topic_semantics import merge_semantic_snapshot
        manual=[{'topic_id':'manifest:backup','title':'备份','navigation_summary':'手工导航'}]
        output=merge_semantic_snapshot(manual,{'source_revision':'r1','topics':[{'topic_id':'manifest:backup','summary':'无关内容','questions':['无关？']}]},'r1')
        self.assertEqual(output,manual)

    def test_empty_review_is_quality_hold_not_worker_failure(self):
        from topic_semantics import semantic_result
        self.assertEqual(semantic_result([], [{'id':'x'}], 'r1')['status'],'quality_hold')

    def test_recent_low_frequency_entity_survives_popular_entity_limit(self):
        rows=[{'id':str(i),'mention_count':100-i,'latest_source_at':'2026-08-01'} for i in range(30)]
        rows.append({'id':'new','mention_count':1,'latest_source_at':'2026-09-20'})
        result=select_entities(rows,10)
        self.assertEqual(len(result),10)
        self.assertIn('new',{row['id'] for row in result})
        self.assertIn('0',{row['id'] for row in result})
        self.assertEqual(result,select_entities(list(reversed(rows)),10))

    def test_related_entity_does_not_place_an_unrelated_topic_in_a_manifest(self):
        topics=[{'topic_id':'entity:x','title':'猫粮','entities':['猫粮','Evolving Profile'],'source_count':2,'source_locators':[]}]
        row=build_manifest_topics(topics,[{'id':'architecture','title':'EP','aliases':['Evolving Profile'],'questions':['如何演进？']}])[0]
        self.assertEqual(row['children'],[])

    def test_build_topic_preserves_raw_source_locators_and_relation_summary(self):
        row=build_topic({
            'id':'e1','canonical_name':'小黛','mention_count':8,
            'first_seen':'2026-07-01T00:00:00Z','last_seen':'2026-09-01T00:00:00Z',
            'fact_types':{'world':3,'experience':5},'source_count':6,
            'related':['飞书','CardKit'],'source_locators':[{'memory_id':'m1','document_id':'d1'}],
        })
        self.assertEqual(row['topic_id'],'entity:e1')
        self.assertIn('飞书',row['overview'])
        self.assertEqual(row['source_locators'][0]['memory_id'],'m1')
        self.assertEqual(row['coverage'],{'sampled':1,'total':6})

    def test_uncomputed_catalog_states_are_unknown_not_clean(self):
        topic=build_topic({'id':'1','canonical_name':'备份','source_count':2,'source_locators':[]})
        self.assertIsNone(topic['pending_changes'])
        self.assertIsNone(topic['conflicts'])
        self.assertIsNone(topic['children'])
        self.assertEqual(topic['content_status'],'entity_navigation_only')

    def test_manifest_aggregates_sources_without_asserting_fact_state(self):
        topics=[
            {'topic_id':'entity:1','title':'Evolving Profile','entities':['Evolving Profile','Hindsight'],'source_count':3,'source_locators':[{'memory_id':'m1','document_id':'d1'}],'time_range':{'start':'2026-08-01','end':'2026-09-01'}},
            {'topic_id':'entity:2','title':'Query Controller','entities':['Query Controller'],'source_count':2,'source_locators':[{'memory_id':'m2','document_id':'d2'}],'time_range':{'start':'2026-08-20','end':'2026-09-10'}},
        ]
        manifests=[{'id':'architecture','title':'Evolving Profile 架构与演进','aliases':['Evolving Profile','Hindsight','Query Controller'],'questions':['系统如何演进？','哪些名称属于兼容层？']}]
        row=build_manifest_topics(topics,manifests)[0]
        self.assertEqual(row['topic_id'],'manifest:architecture')
        self.assertEqual(row['content_status'],'reviewed_navigation_manifest')
        self.assertEqual(row['source_count'],2)
        self.assertEqual(row['source_count_semantics'],'sampled_unique_documents_lower_bound')
        self.assertIsNone(row['coverage']['total'])
        self.assertEqual({item['memory_id'] for item in row['source_locators']},{'m1','m2'})
        self.assertIn('系统如何演进',row['overview'])
        self.assertNotIn('当前状态为',row['overview'])


if __name__=='__main__':unittest.main()
