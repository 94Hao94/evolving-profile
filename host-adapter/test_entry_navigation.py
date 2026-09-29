import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import entry_navigation
from entry_navigation import build_navigation_map
from lib.memory_policy import classify_memory_policy


class EntryNavigationTest(unittest.TestCase):
    def test_all_corpus_domains_are_visible_within_budget_and_have_l1_targets(self):
        with sqlite3.connect(self.catalog) as db:
            db.execute('CREATE TABLE catalog_meta (key,value_json)')
            db.execute('INSERT INTO catalog_meta VALUES(?,?)',('snapshot',json.dumps({'hierarchy_coverage':{'total_memory_count':45000,'indexed_memory_count':44990,'unassigned_memory_count':10}})))
            for i in range(12):
                db.execute('INSERT INTO topics VALUES(?,?,?)',(f'domain:{i:02}',json.dumps({
                    'title':f'领域{i:02}','navigation_summary':'这里有某个领域的长期资料、旧记录及变化线索',
                    'level':'L0','content_status':'source_linked_navigation','children':[f'topic:{i}'],
                    'memory_count':100,'source_count':20,'child_previews':[{'topic_id':f'topic:{i}','title':'子目录'}],
                }),'2026-09-20'))
        context,receipt=build_navigation_map(self.config,classify_memory_policy('你好'),catalog_path=self.catalog)
        for i in range(12):self.assertIn(f'domain:{i:02}',context)
        self.assertLessEqual(len(context),entry_navigation.MAX_CONTEXT_CHARS)
        self.assertEqual(receipt['bank']['hierarchy_coverage']['unassigned_memory_count'],10)
        self.assertEqual(receipt['bank']['topics'][0]['children'],['topic:0'])

    def test_refresh_status_never_claims_current_on_failure_staleness_or_revision_mismatch(self):
        now=datetime(2026,9,20,1,0,tzinfo=timezone.utc)
        state_path=self.catalog.with_suffix('.refresh.json')
        metadata={'revision':'v2','generated_at':'2026-09-20T00:58:00+00:00'}
        cases=(('ready','v2','2026-09-20T00:59:50+00:00','checked'),
               ('failed','v2','2026-09-20T00:59:50+00:00','failed'),
               ('refreshing','v2','2026-09-20T00:59:50+00:00','refreshing'),
               ('ready','v2','2026-09-20T00:50:00+00:00','stale'),
               ('ready','v1','2026-09-20T00:59:50+00:00','unknown'))
        for status,revision,checked,want in cases:
            state_path.write_text(json.dumps({'status':status,'snapshot_revision':revision,'checked_at':checked,'stale_after_seconds':180}))
            self.assertEqual(entry_navigation.catalog_freshness(self.catalog,metadata,now)['status'],want)

    def test_preference_revision_change_is_seen_next_read_without_refresh_worker(self):
        _,before=build_navigation_map(self.config,classify_memory_policy('你好'),catalog_path=self.catalog)
        with sqlite3.connect(self.registry) as db:
            db.execute("UPDATE unit_revisions SET revision='r2',payload_json=json_set(payload_json,'$.text','讲解算法时先给实际例子') WHERE unit_id='p1'")
            db.execute("UPDATE unit_audits SET revision='r2' WHERE unit_id='p1'")
        context,after=build_navigation_map(self.config,classify_memory_policy('你好'),catalog_path=self.catalog)
        self.assertIn('讲解算法',context)
        self.assertNotEqual(before['preferences']['revision'],after['preferences']['revision'])

    def test_distinct_late_scope_is_visible_even_after_many_similar_preferences(self):
        with sqlite3.connect(self.registry) as db:
            for i in range(20):
                payload={'text':f'排版时检查第{i}部分的段落间距', 'primary_category':'delivery', 'applies_when':['处理文档格式']}
                if i==19: payload={'text':'配音需检查音频响度','primary_category':'delivery','applies_when':['录制语音课程']}
                db.execute('INSERT INTO unit_revisions VALUES(?,?,?,1)',(f'd{i:02d}','r1',json.dumps(payload)))
                db.execute('INSERT INTO unit_audits VALUES(?,?,?)',(f'd{i:02d}','r1','approved'))
        context,_=build_navigation_map(self.config,classify_memory_policy('你好'),catalog_path=self.catalog)
        self.assertIn('录制语音课程',context)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.registry = root / 'guidance.sqlite3'
        self.catalog = root / 'topics.sqlite3'
        self.config = root / 'guidance.json'
        self.config.write_text(json.dumps({'registry': str(self.registry)}))
        with sqlite3.connect(self.registry) as db:
            db.executescript('''
                CREATE TABLE unit_revisions (unit_id,revision,payload_json,active);
                CREATE TABLE unit_audits (unit_id,revision,state);
                CREATE TABLE model_revisions (active);
            ''')
            for identity, state, text in (
                ('p1', 'approved', '复杂原理先解释因果，再配具体例子'),
                ('p2', 'needs_review', 'UNREVIEWED PRIVATE BODY'),
            ):
                payload = {'text':text, 'primary_category':'learning', 'applies_when':['学习陌生概念'],
                           'evidence_refs':[{'quote':'RAW SOURCE MUST NOT CROSS ENTRY'}]}
                db.execute('INSERT INTO unit_revisions VALUES(?,?,?,1)', (identity,'r1',json.dumps(payload)))
                db.execute('INSERT INTO unit_audits VALUES(?,?,?)', (identity,'r1',state))
        with sqlite3.connect(self.catalog) as db:
            db.execute('CREATE TABLE topics (topic_id,payload_json,updated_at)')
            db.execute('INSERT INTO topics VALUES(?,?,?)', ('manifest:backup',json.dumps({
                'title':'备份与恢复', 'overview':'可导航问题：\n- 以前怎样验证恢复？',
                'content_status':'reviewed_navigation_manifest', 'source_locators':[{'quote':'BANK RAW BODY'}],
            }),'2026-09-20'))

    def test_local_map_exposes_content_clues_without_source_or_unreviewed_bodies(self):
        with patch('socket.socket', side_effect=AssertionError('network used')):
            context, receipt = build_navigation_map(self.config, classify_memory_policy('你好'), catalog_path=self.catalog)
        self.assertIn('因果', context)
        self.assertIn('以前怎样验证恢复', context)
        self.assertNotIn('UNREVIEWED PRIVATE BODY', context)
        self.assertNotIn('RAW SOURCE', context)
        self.assertNotIn('BANK RAW BODY', context)
        self.assertEqual(receipt['preferences']['approved_count'], 1)
        self.assertEqual(receipt['preferences']['withheld_count'], 1)
        self.assertEqual(receipt['bank']['topic_count'], 1)

    def test_independent_prohibitions_prevent_opening_the_corresponding_store(self):
        cases = (
            ('不要使用任何记忆', False, False),
            ('不要使用我的偏好，请查上次备份', False, True),
            ('不要使用历史事实，但允许协作偏好', True, False),
            ('不要调用 catalog', True, False),
            ('不用 research，允许 recall', True, True),
            ('把“不要使用任何记忆”翻译成英文', True, True),
        )
        original = entry_navigation._connect
        for prompt, preferences, bank in cases:
            def guarded(path):
                if (Path(path) == self.registry and not preferences) or (Path(path) == self.catalog and not bank):
                    raise AssertionError('forbidden store opened')
                return original(path)
            with self.subTest(prompt=prompt), patch.object(entry_navigation, '_connect', side_effect=guarded):
                context, receipt = build_navigation_map(self.config, classify_memory_policy(prompt), catalog_path=self.catalog)
            self.assertEqual('因果' in context, preferences)
            self.assertEqual('以前怎样验证恢复' in context, bank)
            self.assertEqual(receipt['preferences']['status'], 'available' if preferences else 'forbidden')
            self.assertEqual(receipt['bank']['status'], 'available' if bank else 'forbidden')

    def test_missing_catalog_is_unknown_and_does_not_disable_preference_index(self):
        missing = Path(self.temp.name) / 'not-created.sqlite3'
        context, receipt = build_navigation_map(self.config, classify_memory_policy('解释原理'), catalog_path=missing)
        self.assertFalse(missing.exists())
        self.assertIn('因果', context)
        self.assertEqual(receipt['bank']['status'], 'unavailable')
        self.assertNotIn('topic_count', receipt['bank'])


if __name__ == '__main__':
    unittest.main()
