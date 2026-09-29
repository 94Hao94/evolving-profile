from __future__ import annotations
from datetime import datetime,timezone
THRESHOLDS={'retain_outbox':(300,1800),'capsule':(120,600),'projection':(60,300)}
def classify(name,age_seconds):
 healthy,critical=THRESHOLDS[name]
 return 'healthy' if age_seconds<healthy else ('attention' if age_seconds<=critical else 'critical')
def alert(name,age_seconds,scope='global'):
 return {'queue':name,'status':classify(name,age_seconds),'first_seen_at':datetime.now(timezone.utc).isoformat(),'oldest_item_at':None,'affected_scope':scope,'last_success_at':None,'retry_count':0,'next_action':'reconcile' if age_seconds>=THRESHOLDS[name][0] else 'none','recovery_receipt':None}
