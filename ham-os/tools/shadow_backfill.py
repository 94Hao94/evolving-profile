#!/usr/bin/env python3
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ham.api import Api
from ham.events import deterministic_slice
from ham.capsules import build_capsule
api=Api(); rows=api.ledger.conn.execute('SELECT payload_json FROM events ORDER BY session_id,sequence').fetchall(); events=[json.loads(r[0]) for r in rows]
for e in events: api.ledger.save_slice(deterministic_slice(e,0))
tasks=sorted({e['task_id'] for e in events})
for t in tasks: api.ledger.save_capsule(build_capsule(t,api.ledger.latest_events(t),0))
print(json.dumps({'events':len(events),'slices':len(events),'task_capsules':len(tasks)},ensure_ascii=False))
