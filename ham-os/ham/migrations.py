from __future__ import annotations
import hashlib,json
from pathlib import Path
from .capsules import build_capsule
from .contracts import utcnow

def task_id(record): return 'handoff-'+hashlib.sha256((str(record.get('session_id',''))+'|'+str(record.get('project',''))).encode()).hexdigest()[:24]
def provisional(record):
 tid=task_id(record); now=utcnow()
 return {'schema':'ham.task_capsule.v1','task_id':tid,'canonical_task_id':tid,'aliases':[],'identity_evidence_ids':[],'capsule_version':1,'title':'','objective':{'value':str(record.get('current_goal') or ''),'evidence_ids':[]},'current_state':{'value':str(record.get('latest_result') or ''),'evidence_ids':[],'verified_at':str(record.get('updated_at') or now)},'completed_steps':[],'decisions':[{'value':x,'evidence_ids':[]} for x in record.get('recent_decisions') or []],'artifacts':[{'value':x,'evidence_ids':[]} for x in (record.get('references') or {}).get('paths') or []],'failures_and_fixes':[],'open_items':[{'value':x,'evidence_ids':[]} for x in record.get('open_items') or []],'next_action':{'value':(record.get('open_items') or [''])[0],'evidence_ids':[]},'source_threads':[str(record.get('session_id') or '')],'coverage':{'migration':'provisional','source':'task-handoffs.json'},'valid_from':now,'last_verified_at':now,'supersedes_version':None,'status':'unknown','migration_provenance':{'source_path':str(record.get('transcript_path') or ''),'source_record_id':record.get('id')}}
def migrate(ledger,path:Path,dry_run=True):
 source=json.loads(Path(path).read_text()); records=[x for x in source.get('records',[]) if isinstance(x,dict)]; capsules=[provisional(x) for x in records]
 if not dry_run:
  for c in capsules: ledger.save_capsule(c)
 return {'source_records':len(records),'capsules':len(capsules),'dry_run':dry_run,'down_read_source_unchanged':True,'sample_task_ids':[c['task_id'] for c in capsules[:3]]}
