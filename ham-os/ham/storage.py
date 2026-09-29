from __future__ import annotations
import json,sqlite3,time,threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from .contracts import ContractError,digest,validate_event,utcnow

TABLES=('events','event_slices','blobs','projects','project_aliases','tasks','task_relations','task_capsules','artifacts','artifact_versions','memory_links','query_executions','query_facets','coverage_receipts','memory_packs','injection_receipts','usage_feedback','outbox','jobs','tombstones','schema_migrations')
class IdempotencyConflict(ContractError): pass
class Ledger:
 def __init__(self,path:Path):
  self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.lock=threading.RLock(); self.conn=sqlite3.connect(str(self.path),isolation_level=None,check_same_thread=False); self.conn.row_factory=sqlite3.Row
  self.conn.execute('PRAGMA journal_mode=WAL'); self.conn.execute('PRAGMA foreign_keys=ON'); self.migrate()
 @contextmanager
 def transaction(self):
  # isolation_level=None otherwise makes the connection context a no-op.
  with self.lock:
   self.conn.execute('BEGIN IMMEDIATE')
   try:
    yield
    self.conn.commit()
   except BaseException:
    self.conn.rollback()
    raise
 def migrate(self):
  with self.transaction():
   self.conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
   self.conn.execute('CREATE TABLE IF NOT EXISTS blobs(hash TEXT PRIMARY KEY,size INTEGER NOT NULL,mime TEXT,preview TEXT,created_at TEXT NOT NULL)')
   self.conn.execute('''CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY,idempotency_key TEXT UNIQUE NOT NULL,payload_hash TEXT NOT NULL,principal_id TEXT NOT NULL,agent_id TEXT NOT NULL,session_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,sequence INTEGER NOT NULL,origin_class TEXT NOT NULL,event_type TEXT NOT NULL,occurred_at TEXT NOT NULL,recorded_at TEXT NOT NULL,status TEXT NOT NULL,payload_json TEXT NOT NULL, UNIQUE(session_id,sequence))''')
   if 'commit_order' not in {r['name'] for r in self.conn.execute('PRAGMA table_info(events)')}:
    self.conn.execute('''CREATE TABLE events_ordered(commit_order INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,idempotency_key TEXT UNIQUE NOT NULL,payload_hash TEXT NOT NULL,principal_id TEXT NOT NULL,agent_id TEXT NOT NULL,session_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,sequence INTEGER NOT NULL,origin_class TEXT NOT NULL,event_type TEXT NOT NULL,occurred_at TEXT NOT NULL,recorded_at TEXT NOT NULL,status TEXT NOT NULL,payload_json TEXT NOT NULL)''')
    # Existing payloads and IDs remain byte-for-byte intact. The old sequence
    # could be a hash; rowid is the only recorded insertion order available.
    self.conn.execute('INSERT INTO events_ordered SELECT rowid,* FROM events ORDER BY rowid')
    self.conn.execute('DROP TABLE events')
    self.conn.execute('ALTER TABLE events_ordered RENAME TO events')
   self.conn.execute('CREATE INDEX IF NOT EXISTS events_task_order ON events(task_id,commit_order)')
   self.conn.execute('CREATE TABLE IF NOT EXISTS event_slices(slice_id TEXT PRIMARY KEY,event_id TEXT NOT NULL,slice_index INTEGER NOT NULL,extractor_version TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL,UNIQUE(event_id,slice_index,extractor_version))')
   self.conn.execute('CREATE TABLE IF NOT EXISTS task_capsules(task_id TEXT NOT NULL,capsule_version INTEGER NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL,PRIMARY KEY(task_id,capsule_version))')
   self.conn.execute('CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,next_attempt_at REAL NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL)')
   self.conn.execute('CREATE TABLE IF NOT EXISTS query_executions(execution_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,progress_version INTEGER NOT NULL,status TEXT NOT NULL,updated_at TEXT NOT NULL)')
   for name in set(TABLES)-{'schema_migrations','blobs','events','event_slices','task_capsules','outbox','query_executions'}: self.conn.execute(f'CREATE TABLE IF NOT EXISTS {name}(id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,created_at TEXT NOT NULL)')
   self.conn.execute("INSERT OR IGNORE INTO schema_migrations VALUES('ham-ledger-v1',datetime('now'))")
   self.conn.execute("INSERT OR IGNORE INTO schema_migrations VALUES('ham-occurrence-order-v2',datetime('now'))")
 def event_payload(self,event_id:str):
  with self.lock:
   row=self.conn.execute('SELECT payload_json FROM events WHERE event_id=?',(event_id,)).fetchone()
   return json.loads(row[0]) if row else None
 def next_capsule_version(self,task_id:str)->int:
  with self.lock:
   row=self.conn.execute('SELECT max(capsule_version) FROM task_capsules WHERE task_id=?',(task_id,)).fetchone()
   return int(row[0] or 0)
 def latest_capsule(self,task_id:str):
  with self.lock:
   row=self.conn.execute('SELECT payload_json FROM task_capsules WHERE task_id=? ORDER BY capsule_version DESC LIMIT 1',(task_id,)).fetchone()
   return json.loads(row[0]) if row else None
 def save_execution(self,execution_id:str,payload:dict[str,Any]):
  with self.lock,self.conn:
   self.conn.execute('INSERT OR REPLACE INTO query_executions VALUES(?,?,?,?,?)',(execution_id,json.dumps(payload,ensure_ascii=False,sort_keys=True),int(payload.get('progress_version',1)),payload.get('execution_status','running'),utcnow()))
 def get_execution(self,execution_id:str):
  with self.lock:
   row=self.conn.execute('SELECT payload_json FROM query_executions WHERE execution_id=?',(execution_id,)).fetchone()
   return json.loads(row[0]) if row else None
 def save_pack(self,pack_id:str,payload:dict[str,Any]):
  with self.lock,self.conn:
   self.conn.execute('INSERT OR REPLACE INTO memory_packs(id,payload_json,created_at) VALUES(?,?,?)',(pack_id,json.dumps(payload,ensure_ascii=False,sort_keys=True),utcnow()))
 def get_pack(self,pack_id:str):
  with self.lock:
   row=self.conn.execute('SELECT payload_json FROM memory_packs WHERE id=?',(pack_id,)).fetchone()
   return json.loads(row[0]) if row else None
 def save_feedback(self,feedback_id:str,payload:dict[str,Any]):
  with self.lock,self.conn:
   self.conn.execute('INSERT INTO usage_feedback(id,payload_json,created_at) VALUES(?,?,?)',(feedback_id,json.dumps(payload,ensure_ascii=False,sort_keys=True),utcnow()))
 def append_event(self,payload:dict[str,Any])->dict[str,Any]:
  payload=validate_event(dict(payload)); h=digest({k:v for k,v in payload.items() if k not in {'recorded_at','status'}}); started=time.perf_counter()
  with self.transaction():
   old=self.conn.execute('SELECT event_id,payload_hash FROM events WHERE idempotency_key=?',(payload['idempotency_key'],)).fetchone()
   if old:
    if old['payload_hash']!=h: raise IdempotencyConflict('idempotency_conflict')
    return {'event_id':old['event_id'],'durable':True,'idempotent_replay':True,'elapsed_ms':round((time.perf_counter()-started)*1000,3)}
   self.conn.execute('INSERT INTO events(event_id,idempotency_key,payload_hash,principal_id,agent_id,session_id,project_id,task_id,sequence,origin_class,event_type,occurred_at,recorded_at,status,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(payload['event_id'],payload['idempotency_key'],h,payload['principal_id'],payload['agent_id'],payload['session_id'],payload['project_id'],payload['task_id'],payload['sequence'],payload['origin_class'],payload['event_type'],payload['occurred_at'],payload['recorded_at'],'persisted',json.dumps(payload,ensure_ascii=False,sort_keys=True)))
   self.conn.execute('INSERT INTO outbox(event_id,kind,status,next_attempt_at,payload_json,created_at) VALUES(?,?,?,?,?,?)',(payload['event_id'],'enrichment','pending',time.time(),json.dumps({'event_id':payload['event_id']}),payload['recorded_at']))
  return {'event_id':payload['event_id'],'durable':True,'idempotent_replay':False,'elapsed_ms':round((time.perf_counter()-started)*1000,3)}
 def latest_events(self,task_id:str,limit:int=50)->list[dict[str,Any]]:
  with self.lock:
   rows=self.conn.execute('SELECT payload_json FROM events WHERE task_id=? ORDER BY commit_order DESC',(task_id,)).fetchall()
  ordered=[json.loads(r[0]) for r in rows]
  # Source sequence is meaningful only inside its source session. Reorder
  # those slots, never compare source clocks across unrelated sessions.
  slots={}
  for i,event in enumerate(ordered):
   if type(event.get('source_sequence')) is int:
    slots.setdefault((event['agent_id'],event['session_id']),[]).append(i)
  for indexes in slots.values():
   events=sorted((ordered[i] for i in indexes),key=lambda e:e['source_sequence'],reverse=True)
   for i,event in zip(indexes,events): ordered[i]=event
  return ordered[:max(0,min(200,limit))]
 def outbox_health(self)->dict[str,Any]:
  with self.lock: r=self.conn.execute("SELECT count(*),min(created_at) FROM outbox WHERE status='pending'").fetchone(); return {'pending':r[0],'oldest_item_at':r[1]}
 def close(self):
  with self.lock: self.conn.close()
 def pending_outbox(self,limit=100):
  with self.lock: return [dict(r) for r in self.conn.execute("SELECT * FROM outbox WHERE status='pending' ORDER BY id LIMIT ?",(min(200,limit),)).fetchall()]
 def ack_outbox(self,row_id,status='shadow_recorded'):
  with self.lock,self.conn: self.conn.execute('UPDATE outbox SET status=?,attempts=attempts+1 WHERE id=?',(status,row_id))
 def save_slice(self,slice_payload):
  with self.lock,self.conn: self.conn.execute('INSERT OR IGNORE INTO event_slices VALUES(?,?,?,?,?,?)',(slice_payload['slice_id'],slice_payload['event_id'],slice_payload['slice_index'],slice_payload['extractor_version'],json.dumps(slice_payload,ensure_ascii=False),slice_payload['status']))
 def save_capsule(self,capsule):
  with self.lock,self.conn: self.conn.execute('INSERT OR REPLACE INTO task_capsules VALUES(?,?,?,?)',(capsule['task_id'],capsule['capsule_version'],json.dumps(capsule,ensure_ascii=False),capsule['status']))
