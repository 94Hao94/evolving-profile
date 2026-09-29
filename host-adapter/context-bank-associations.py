#!/usr/bin/env python3
"""Read-only export of Bank record → Session/Project Context links."""
import argparse, concurrent.futures, hashlib, json, os, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from lib.context_associations import write_association_snapshot

def pkey(value):
    return hashlib.sha256(str(value or '').encode()).hexdigest()[:16] if value else ''

def fetch(url, offset):
    with urllib.request.urlopen(url + '&offset=' + str(offset), timeout=30) as response:
        return json.load(response)

parser=argparse.ArgumentParser(); parser.add_argument('--bank', default='personal-memory'); parser.add_argument('--index', default=os.path.expanduser('~/.evolving-profile/context/context-index.json')); parser.add_argument('--output', default=os.path.expanduser('~/.evolving-profile/context/context-bank-associations.json')); args=parser.parse_args()
index=json.loads(Path(args.index).read_text()); sessions={str(x.get('session_id')):x for x in index.get('sessions',[]) if x.get('session_id')}; projects={str(x.get('project_key')):x for x in index.get('projects',[]) if x.get('project_key')}
base='http://127.0.0.1:12088/v1/default/banks/'+urllib.parse.quote(args.bank,safe='')+'/memories/list?limit=1000'
with urllib.request.urlopen(base+'&offset=0',timeout=30) as response: first=json.load(response)
total=int(first.get('total') or 0); pages={0:first}; offsets=list(range(1000,total,1000))
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    for offset,data in zip(offsets,pool.map(lambda o: fetch(base,o), offsets)): pages[offset]=data
links=[]; unresolved=[]
for offset in sorted(pages):
    for row in pages[offset].get('items') or []:
        meta=row.get('metadata') or {}; ids=meta.get('session_ids') or meta.get('session_id') or []
        if isinstance(ids,str): ids=[v.strip() for v in ids.split(',') if v.strip()]
        matched_sessions=[str(v) for v in ids if str(v) in sessions]
        raw_project=meta.get('project') or meta.get('cwd') or ''; key=str(meta.get('project_key') or pkey(raw_project)); matched_project=key if key in projects else ''
        if not matched_sessions and not matched_project: continue
        links.append({'record_id':str(row.get('id')),'record_type':str(row.get('fact_type') or row.get('type') or 'unknown'),'session_ids':matched_sessions,'project_key':matched_project or None,'source_ids':[str(v) for v in (row.get('document_id'),row.get('chunk_id')) if v],'at':row.get('occurred_start') or row.get('mentioned_at') or row.get('updated_at')})
payload={'schema':'evolving-profile.context-bank-associations.v1','bank':args.bank,'scanned_records':total,'linked_records':len(links),'links':links,'policy':'read_only_association_no_bank_rewrite','indexed_at':datetime.now(timezone.utc).isoformat(),'source_index_updated_at':index.get('updated_at')}
out=Path(args.output); write_association_snapshot(out,payload)
print(json.dumps({'ok':True,'scanned_records':total,'linked_records':len(links),'output':str(out)},ensure_ascii=False))
