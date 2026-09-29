from __future__ import annotations
from .contracts import utcnow

def build_capsule(task_id,events,previous_version=0):
 # Ledger supplies latest-first, with source-local order already resolved.
 # A legacy sequence can be a hash, not a clock.
 ordered=list(reversed(events)); evidence=[e['event_id'] for e in ordered]
 last=ordered[-1] if ordered else None
 return {'schema':'ham.task_capsule.v1','task_id':task_id,'canonical_task_id':task_id,'aliases':[],'identity_evidence_ids':evidence,'capsule_version':previous_version+1,'title':'','objective':{'value':'','evidence_ids':[]},'current_state':{'value':last['body_preview'] if last else '', 'evidence_ids':[last['event_id']] if last else [],'verified_at':None,'semantics':'latest_captured_statement_not_verified_state'},'completed_steps':[],'decisions':[],'artifacts':[],'failures_and_fixes':[],'open_items':[],'next_action':{'value':'','evidence_ids':[]},'source_threads':sorted(set(e['session_id'] for e in ordered)),'coverage':{'event_count':len(ordered)},'valid_from':utcnow(),'last_verified_at':None,'supersedes_version':previous_version or None,'status':'unknown'}
