import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_workspace import read_page, explicit_anchor_terms


class EvidenceWorkspaceTest(unittest.TestCase):
    def test_unread_page_is_optional_when_answer_evidence_may_be_sufficient(self):
        rid=str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as root:
            Path(root,rid+'.json').write_text(json.dumps({
                'bank':'bank','created_at':9_999_999_999,'status':'discovered_not_verified',
                'memory_ids':['first','second'],'invalid_reference_ids':[],
                'query':'某项目的两个预算版本分别属于什么阶段',
                'seconds':0.1,'tool_call_count':1,
            }),encoding='utf-8')
            page=read_page('bank',rid,0,lambda path,timeout=8:{
                'id':path.rsplit('/',1)[-1],'state':'valid','text':'预算方案片段','metadata':{},
            },root,page_size=1)
        self.assertEqual(page['query_completion'],'unread_candidates')
        self.assertEqual(page['next_offset'],1)
        self.assertEqual(page['remaining_candidate_count'],1)
        self.assertTrue(page['next_action']['optional'])
        self.assertEqual(page['next_action']['when'],'required_evidence_gap_remains')
        self.assertEqual(page['next_action']['stop_when'],'requested_slots_supported_or_conflicts_reported')

    def test_concurrent_pages_never_restore_an_unrelated_withdrawn_snapshot(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        started,release=Event(),Event()
        rid=str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as root:
            path=Path(root,rid+'.json')
            path.write_text(json.dumps({'bank':'bank','created_at':9_999_999_999,
                'status':'discovered_not_verified','memory_ids':['a','b'],'invalid_reference_ids':[],
                'query':'test','seconds':0.1,'tool_call_count':1,
                'candidate_audit':[{'id':mid,'text':'OLD BODY '+mid,'outcome':'discovered'} for mid in ['a','b']]}))
            def api(p,timeout=8):
                mid=p.rsplit('/',1)[-1]
                if mid=='b':
                    started.set()
                    if not release.wait(5): raise RuntimeError('test synchronization timed out')
                    return {'id':'b','state':'valid','text':'body b','metadata':{}}
                return {'id':'a','state':'invalidated','text':'withdrawn body','metadata':{}}
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending=pool.submit(read_page,'bank',rid,1,api,root,1)
                self.assertTrue(started.wait(5))
                read_page('bank',rid,0,api,root,1)
                release.set();pending.result(timeout=5)
            rows={row['id']:row for row in json.loads(path.read_text())['candidate_audit']}
        self.assertEqual(rows['a']['reason'],'withdrawn')
        self.assertEqual(rows['a']['text'],'')

    def test_literal_miss_is_uncertain_not_automatic_empty_and_audit_is_saved(self):
        rid=str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as root:
            path=Path(root,rid+'.json')
            path.write_text(json.dumps({'bank':'bank','created_at':9_999_999_999,'status':'discovered_not_verified',
                'memory_ids':['a','b'],'invalid_reference_ids':[],'query':'鹏飞学校项目',
                'explicit_anchor_terms':['鹏飞学校'],'seconds':0.1,'tool_call_count':1}))
            def api(path,timeout=8):
                mid=path.rsplit('/',1)[-1]
                return {'id':mid,'state':'valid' if mid=='a' else 'invalidated',
                        'text':'这个学校的方案设计要求先看业务阶段','metadata':{}}
            page=read_page('bank',rid,0,api,root,page_size=2)
            self.assertEqual([row['id'] for row in page['memories']],['a'])
            self.assertEqual(page['memories'][0]['relevance']['state'],'uncertain')
            state=json.loads(path.read_text())
            self.assertEqual(len(state['candidate_audit']),2)
            self.assertEqual(state['candidate_audit'][1]['text'],'')

    def test_entity_beyond_preview_is_not_lost_by_preview_truncation(self):
        rid=str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as root:
            Path(root,rid+'.json').write_text(json.dumps({'bank':'bank','created_at':9_999_999_999,
                'status':'discovered_not_verified','memory_ids':['a'],'invalid_reference_ids':[],
                'query':'天津农学院','explicit_anchor_terms':['天津农学院'],'seconds':0.1,'tool_call_count':1}))
            page=read_page('bank',rid,0,lambda *args,**kwargs:{'id':'a','state':'valid',
                'text':'前文'*800+'天津农学院项目背景','metadata':{}},root,page_size=1)
        self.assertEqual(page['memories'][0]['relevance']['state'],'literal_match')
        self.assertTrue(page['memories'][0]['text_truncated'])

    def test_open_profile_inventory_does_not_use_entire_question_as_anchor(self):
        query = '用户问“现在写方案你都有什么对我的了解”。请盘点用户写高校/政企方案时的长期偏好。'
        self.assertEqual(explicit_anchor_terms(query), [])

    def test_relationship_question_extracts_entity_instead_of_full_sentence(self):
        self.assertEqual(explicit_anchor_terms('用户问“我和PPT有什么关系”。查相关历史记录。'), ['ppt'])
        self.assertEqual(explicit_anchor_terms('用户问“我跟具身智能什么关系”。查相关历史记录。'), ['具身智能'])

    def test_relationship_grammar_is_not_part_of_named_institution(self):
        for query in (
            '用户本人（liuzhongyang）与天津农学院是什么关系？',
            '我与天津农学院的关系；包括天津农学院 智慧教室 项目、工作、客户关系。',
            '我和河北工业大学是什么关系？',
            '我跟天津职业技术师范大学有什么关系？',
        ):
            expected = ('天津农学院' if '天津农学院' in query else
                        '河北工业大学' if '河北工业大学' in query else '天津职业技术师范大学')
            with self.subTest(query=query):
                self.assertEqual(explicit_anchor_terms(query), [expected])

    def test_grammar_fix_admits_target_but_keeps_other_institution_out(self):
        rid = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as root:
            Path(root, rid + '.json').write_text(json.dumps({
                'bank': 'bank', 'created_at': 9_999_999_999, 'status': 'discovered_not_verified',
                'memory_ids': ['target', 'other'], 'invalid_reference_ids': [],
                'query': '我与天津农学院的关系',
                'explicit_anchor_terms': explicit_anchor_terms('我与天津农学院的关系'),
                'seconds': 0.1, 'tool_call_count': 1,
            }), encoding='utf-8')
            def api(path, timeout=8):
                mid = path.rsplit('/', 1)[-1]
                return {'id': mid, 'state': 'valid', 'metadata': {},
                        'text': '天津农学院智慧教室方案' if mid == 'target' else '河北工业大学方案'}
            page = read_page('bank', rid, 0, api, root, page_size=2)
        self.assertEqual([row['id'] for row in page['memories']], ['target', 'other'])
        self.assertEqual(page['memories'][1]['relevance']['state'], 'uncertain')
        self.assertEqual(page['scope_filter']['rejected_count'], 0)

    def test_read_page_returns_bounded_preview_and_source_locator(self):
        """A one-page candidate response must not put an entire long source into model context."""
        research_id = str(uuid.uuid4())
        memory_id = str(uuid.uuid4())
        long_text = "历史证据" * 2000
        with tempfile.TemporaryDirectory() as root:
            Path(root, f"{research_id}.json").write_text(
                json.dumps(
                    {
                        "research_id": research_id,
                        "bank": "bank",
                        "created_at": 9_999_999_999,
                        "status": "discovered_not_verified",
                        "memory_ids": [memory_id],
                        "invalid_reference_ids": [],
                        "query": "测试",
                        "seconds": 0.1,
                        "tool_call_count": 1,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def api(path, timeout=8):
                return {
                    "id": memory_id,
                    "state": "valid",
                    "text": long_text,
                    "document_id": "document-1",
                    "chunk_id": "chunk-1",
                    "metadata": {},
                }

            page = read_page("bank", research_id, 0, api, root, page_size=1)

        item = page["memories"][0]
        self.assertLess(len(item["text"]), len(long_text))
        self.assertTrue(item["text_truncated"])
        self.assertEqual(item["source_locator"], {"memory_id": memory_id, "document_id": "document-1", "chunk_id": "chunk-1"})

    def test_explicit_entity_query_rejects_semantically_unrelated_candidates(self):
        research_id = str(uuid.uuid4())
        mismatch_id, direct_id = str(uuid.uuid4()), str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as root:
            Path(root, f"{research_id}.json").write_text(json.dumps({
                "research_id": research_id, "bank": "bank", "created_at": 9_999_999_999,
                "status": "discovered_not_verified", "memory_ids": [mismatch_id, direct_id],
                "invalid_reference_ids": [], "query": "鹏飞学校有没有历史记录",
                "explicit_anchor_terms": ["鹏飞学校"], "seconds": 0.1, "tool_call_count": 1,
            }, ensure_ascii=False), encoding="utf-8")
            def api(path, timeout=8):
                mid=path.rsplit('/',1)[-1]
                return {"id":mid,"state":"valid","text":"系统架构和检索机制记录" if mid==mismatch_id else "鹏飞学校方案记录",
                        "document_id":"document-1","chunk_id":"chunk-1","metadata":{}}
            page=read_page("bank",research_id,0,api,root,page_size=2)
        self.assertEqual([row["id"] for row in page["memories"]],[direct_id,mismatch_id])
        self.assertEqual(page['memories'][1]['relevance']['state'],'uncertain')
        self.assertEqual(page["scope_filter"]["rejected_count"],0)
