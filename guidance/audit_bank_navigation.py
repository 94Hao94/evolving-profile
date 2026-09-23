"""Read-only audit: corpus ID coverage, tree edges, evidence and query routes."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'host-adapter'))
from topic_catalog import TopicCatalog
from entry_navigation import build_navigation_map,MAX_CONTEXT_CHARS
from observation_rebuild import load_env,atomic


def audit(output):
    import psycopg2
    bank='personal-memory'
    catalog=TopicCatalog(Path.home()/'.evolving-profile/catalog/topics.sqlite3')
    topics=catalog.list(1000);by_id={r['topic_id']:r for r in topics}
    roots=[r for r in topics if r.get('level')=='L0'];leaves=[r for r in topics if r.get('level')=='L1']
    errors=[]
    with catalog._connect() as db:
        members=[dict(row) for row in db.execute('SELECT * FROM topic_members')]
    with psycopg2.connect(load_env()['EVOLVING_PROFILE_API_DATABASE_URL'],connect_timeout=3) as db:
        db.set_session(readonly=True)
        with db.cursor() as cur:
            cur.execute('SELECT id::text,document_id FROM memory_units WHERE bank_id=%s',(bank,))
            live=dict(cur.fetchall())
    if set(live)!={r['memory_id'] for r in members}:errors.append('corpus_id_mismatch')
    invalid_targets=[r['memory_id'] for r in members if r['topic_id'] not in by_id]
    if invalid_targets:errors.append('missing_membership_target')
    children={v for root in roots for v in root.get('children') or []}
    if children!={r['topic_id'] for r in leaves}:errors.append('root_to_leaf_gap')
    refs=[v for row in leaves for v in row['source_locators']]
    if any(v['memory_id'] not in live or live[v['memory_id']]!=v.get('document_id') for v in refs):errors.append('invalid_source_locator')
    timings=[]
    for _ in range(5):
        start=time.perf_counter();text,receipt=build_navigation_map(Path.home()/'.evolving-profile/guidance-v1/guidance-v1.json',{'history_allowed':True,'guidance_memory_policy':'allowed'})
        timings.append(round((time.perf_counter()-start)*1000,2))
    if len(text)>MAX_CONTEXT_CHARS:errors.append('context_budget_exceeded')
    for root in roots:
        if root['topic_id'] not in text:errors.append('root_missing_from_hook')
    queries={q:[{'topic_id':r['topic_id'],'title':r['title']} for r in catalog.search(q,4)] for q in ('家庭','健康','学习','投标','硬件','文档','工具','妻子')}
    if any(not rows for rows in queries.values()):errors.append('empty_navigation_query')
    result={'bank_id':bank,'corpus_records':len(live),'indexed_records':len(members),'root_count':len(roots),'leaf_count':len(leaves),
            'valid_sample_source_locators':len(refs),'records_without_document':sum(v is None for v in live.values()),
            'hook_chars':len(text),'hook_latency_ms':timings,'queries':queries,'errors':errors,
            'scope':'structural_and_source_integrity; not exhaustive semantic or answer-quality certification'}
    atomic(Path(output),result);print(json.dumps(result,ensure_ascii=False,indent=2))
    if errors:raise SystemExit(1)


if __name__=='__main__':audit(sys.argv[1])
