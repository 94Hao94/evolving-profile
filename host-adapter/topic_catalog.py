"""Replaceable topic navigation over Bank evidence; catalog text is not evidence."""
from __future__ import annotations

import json
import hashlib
import re
import os
import shutil
import sqlite3
import tempfile
import uuid
from pathlib import Path

KNOWLEDGE_REVIEW_PATH=Path.home()/'.evolving-profile/catalog/knowledge-page-review.json'

def knowledge_review(page_id:str,path:Path=KNOWLEDGE_REVIEW_PATH)->dict:
    try:return (json.loads(Path(path).read_text(encoding='utf-8')).get('pages') or {}).get(page_id) or {'state':'unreviewed','reason':'source-level review not recorded'}
    except (OSError,ValueError,TypeError):return {'state':'unreviewed','reason':'review registry unavailable'}

def redact_unreviewed_page(page:dict,path:Path=KNOWLEDGE_REVIEW_PATH)->dict:
    value=dict(page or {});review=knowledge_review(str(value.get('id') or value.get('topic_id') or ''),path);value['review']=review
    if review.get('state')!='approved':
        value.pop('body',None);value.pop('markdown',None);value.pop('snippet',None)
        value['content_status']='withheld_pending_source_review'
    return value


def merge_catalog_rows(official_rows:list[dict],entity_rows:list[dict],limit:int)->list[dict]:
    """Round-robin two navigation catalogs and deduplicate stable IDs."""
    lanes=(('hindsight_knowledge_pages',official_rows),('entity_navigation_catalog',entity_rows))
    decorated=[];seen=set();indices=[0,0];maximum=max(1,int(limit))
    while len(decorated)<maximum and any(indices[i]<len(lanes[i][1]) for i in range(2)):
        for lane_index,(source,rows) in enumerate(lanes):
            if len(decorated)>=maximum or indices[lane_index]>=len(rows):continue
            row=dict(rows[indices[lane_index]]);indices[lane_index]+=1
            stable_id=str(row.get('topic_id') or row.get('id') or '')
            if not stable_id or stable_id in seen:continue
            seen.add(stable_id);row['stable_topic_id']=stable_id;row['catalog_source']=source
            decorated.append(row)
    return decorated


def _terms(value: str) -> set[str]:
    text=str(value or '').casefold()
    result=set(re.findall(r'[a-z][a-z0-9_.+-]{1,}',text))
    for chunk in re.findall(r'[\u4e00-\u9fff]+',text):
        result.add(chunk)
        result.update(chunk[i:i+2] for i in range(max(0,len(chunk)-1)))
    return result


class TopicCatalog:
    def __init__(self, path: Path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS topics (topic_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS catalog_meta (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS entity_index (topic_id TEXT PRIMARY KEY, title TEXT NOT NULL, source_count INTEGER NOT NULL, latest_source_at TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS topic_members (memory_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, topic_id TEXT NOT NULL, source_revision TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS topic_members_topic ON topic_members(topic_id)')

    def _connect(self):
        connection=sqlite3.connect(self.path)
        connection.row_factory=sqlite3.Row
        return connection

    def replace_topics(self, topics: list[dict], metadata: dict | None = None, entity_index: list[dict] | None = None, members: list | None = None):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM topics')
            db.executemany('INSERT INTO topics(topic_id,payload_json,updated_at) VALUES(?,?,?)',[
                (row['topic_id'],json.dumps(self._normalize(row),ensure_ascii=False,sort_keys=True),row.get('refreshed_at')) for row in topics
            ])
            if metadata is not None:
                db.execute('INSERT OR REPLACE INTO catalog_meta VALUES(?,?)',('snapshot',json.dumps(metadata,ensure_ascii=False,sort_keys=True)))
            if entity_index is not None:
                db.execute('DELETE FROM entity_index')
                db.executemany('INSERT INTO entity_index VALUES(?,?,?,?)',[(row['id'],row['title'],int(row.get('source_count') or 0),row.get('latest_source_at')) for row in entity_index])
            if members is not None:
                db.execute('DELETE FROM topic_members')
                db.executemany('INSERT INTO topic_members VALUES(?,?,?,?)',[(row[0],row[1] or '',row[2],row[3]) for row in members])

    def metadata(self):
        with self._connect() as db:
            row=db.execute('SELECT value_json FROM catalog_meta WHERE key=?',('snapshot',)).fetchone()
        return json.loads(row[0]) if row else {}

    def _normalize(self,row):
        return {
            'schema':'evolving-profile.topic.v1','topic_id':row['topic_id'],'title':row.get('title') or row['topic_id'],
            'abstract':row.get('abstract') or '', 'overview':row.get('overview') or '',
            'entities':list(row.get('entities') or []),'time_range':row.get('time_range'),
            'time_range_semantics':row.get('time_range_semantics') or 'unknown',
            'source_count':int(row.get('source_count') or 0),'source_locators':list(row.get('source_locators') or []),
            'source_count_semantics':row.get('source_count_semantics') or 'unique_documents_from_bank_projection',
            'coverage':row.get('coverage') or {'sampled':len(row.get('source_locators') or []),'total':int(row.get('source_count') or 0)},
            'pending_changes':row.get('pending_changes'),'conflicts':row.get('conflicts'),
            'children':row.get('children'),'refreshed_at':row.get('refreshed_at'),
            'navigation_summary':row.get('navigation_summary'),
            'semantic_overview':row.get('semantic_overview'),
            'semantic_status':row.get('semantic_status'),
            'semantic_generated_at':row.get('semantic_generated_at'),
            'level':row.get('level'), 'parent_id':row.get('parent_id'), 'parent_ids':row.get('parent_ids') or [],
            'child_previews':row.get('child_previews') or [],
            'memory_count':row.get('memory_count'), 'fact_types':row.get('fact_types') or {},
            'count_semantics':row.get('count_semantics'),
            'read_more':row.get('read_more'),
            'example_entities':row.get('example_entities') or [],
            'latest_source_at':row.get('latest_source_at'),
            'bank_id':row.get('bank_id'),
            'content_status':row.get('content_status') or 'entity_navigation_only',
            'overview_status':row.get('overview_status') or 'structural_not_semantic_summary',
            'pending_changes_status':row.get('pending_changes_status') or ('not_computed' if row.get('pending_changes') is None else 'computed'),
            'conflict_status':row.get('conflict_status') or ('not_computed' if row.get('conflicts') is None else 'computed'),
            'boundary':'navigation_only_not_fact_evidence',
        }

    def get(self,topic_id):
        with self._connect() as db:row=db.execute('SELECT payload_json FROM topics WHERE topic_id=?',(topic_id,)).fetchone()
        if row:
            value=json.loads(row['payload_json'])
            if value.get('level')=='L1' or topic_id=='domain:pending':value['evidence_page']=self.evidence_page(topic_id)
            return value
        with self._connect() as db:brief=db.execute('SELECT * FROM entity_index WHERE topic_id=?',(topic_id,)).fetchone()
        return {'topic_id':brief['topic_id'],'title':brief['title'],'source_count':brief['source_count'],
                'latest_source_at':brief['latest_source_at'],'content_status':'entity_navigation_only',
                'boundary':'navigation_only_not_fact_evidence','coverage':{'sampled':0,'total':brief['source_count']}} if brief else None

    def evidence_page(self,topic_id,offset=0,limit=8):
        offset=max(0,int(offset));limit=max(1,min(40,int(limit)))
        with self._connect() as db:
            total=db.execute('SELECT count(*) FROM topic_members WHERE topic_id=?',(topic_id,)).fetchone()[0]
            rows=db.execute('SELECT memory_id,document_id FROM topic_members WHERE topic_id=? ORDER BY memory_id LIMIT ? OFFSET ?',(topic_id,limit,offset)).fetchall()
        return {'items':[dict(r) for r in rows],'total':total,'offset':offset,'next_offset':offset+len(rows) if offset+len(rows)<total else None,
                'read_more':'read_source(memory_id); topic membership is a navigation clue, not a verified claim'}

    def list(self,limit=100):
        with self._connect() as db:rows=db.execute("SELECT payload_json FROM topics ORDER BY CASE json_extract(payload_json,'$.level') WHEN 'L0' THEN 0 WHEN 'L1' THEN 1 ELSE 2 END,updated_at DESC,topic_id LIMIT ?",(limit,)).fetchall()
        return [json.loads(row['payload_json']) for row in rows]

    def count(self):
        with self._connect() as db:row=db.execute('SELECT count(*) AS n FROM topics').fetchone()
        return int(row['n'] or 0)

    def index_count(self):
        with self._connect() as db:row=db.execute('SELECT count(*) AS n FROM entity_index').fetchone()
        return int(row['n'] or 0)

    def search(self,query,limit=8):
        query_terms=_terms(query);anchors=[value.casefold() for value in re.findall(r'[a-z][a-z0-9_.+-]{1,}|[\u4e00-\u9fff]{2,}',str(query or '').casefold())];ranked=[]
        for row in self.list(1000):
            title_terms=_terms(row['title']+' '+' '.join(row['entities']))
            body_terms=_terms(row['abstract']+' '+row['overview'])
            phrase=str(query or '').casefold()
            score=6*len(query_terms&title_terms)+2*len(query_terms&body_terms)
            if phrase and phrase in (row['title']+' '+row['abstract']+' '+row['overview']).casefold():score+=8
            title=(row['title']+' '+' '.join(row['entities'])).casefold()
            score+=30*sum(anchor in title for anchor in anchors)
            if score:ranked.append((score,row))
        ranked.sort(key=lambda item:(item[0],item[1]['source_count']),reverse=True)
        output=[row for _,row in ranked[:limit]]
        needle=str(query or '').strip().casefold()
        if needle:
            escaped=needle.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            with self._connect() as db:
                matches=db.execute("SELECT * FROM entity_index WHERE lower(title) LIKE ? ESCAPE '\\' ORDER BY source_count DESC LIMIT ?",('%'+escaped+'%',limit)).fetchall()
            exact=[self.get(row['topic_id']) for row in matches if row['title'].casefold()==needle]
            partial=[self.get(row['topic_id']) for row in matches if row['title'].casefold()!=needle]
            exact_ids={row['topic_id'] for row in exact}
            # A broad query should find the corpus domain before high-frequency
            # entity names that only contain that word (health checks, etc.).
            domains=[row for row in output if row.get('level')=='L0']
            rest=[row for row in output if row.get('level')!='L0' and row['topic_id'] not in exact_ids]
            seen=set();output=[]
            for row in [*exact,*domains,*rest,*partial]:
                if row['topic_id'] not in seen:output.append(row);seen.add(row['topic_id'])
        return output[:limit]

    def project_markdown(self,root:Path):
        root=Path(root);root.parent.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(dir=root.parent,prefix=root.name+'.next-'))
        backup=root.with_name(root.name+'.old-'+uuid.uuid4().hex);names=[]
        try:
            for row in self.list(1000):
                slug=re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff_-]+','-',row['title']).strip('-') or 'topic'
                stable=hashlib.sha256(str(row['topic_id']).encode()).hexdigest()[:10]
                name=f'{slug}-{stable}.md';path=staging/name
                content=(f"---\ntopic_id: {row['topic_id']}\nboundary: navigation_only_not_fact_evidence\n"
                         f"source_count: {row['source_count']}\npending_changes: {row['pending_changes'] if row['pending_changes'] is not None else 'unknown'}\n"
                         f"content_status: {row['content_status']}\n---\n\n"
                         f"# {row['title']}\n\n{row['abstract']}\n\n## 主题概览\n\n{row['overview']}\n")
                path.write_text(content,encoding='utf-8');names.append(name)
            if root.exists():os.replace(root,backup)
            os.replace(staging,root)
            if backup.exists():shutil.rmtree(backup)
            return [root/name for name in names]
        except Exception:
            if not root.exists() and backup.exists():os.replace(backup,root)
            raise
        finally:
            if staging.exists():shutil.rmtree(staging)
