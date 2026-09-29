from __future__ import annotations
import json
from .events import deterministic_slice
from .capsules import build_capsule
from .projection import write_projection

def process(api,limit=100):
 flags=api.flags(); completed=[]
 for row in api.ledger.pending_outbox(limit):
  eid=json.loads(row['payload_json'])['event_id']; event=api.ledger.event_payload(eid)
  if not event: api.ledger.ack_outbox(row['id'],'terminal_failed'); continue
  if flags.get('eventSliceShadow'): api.ledger.save_slice(deterministic_slice(event,0))
  if flags.get('capsuleShadow'):
   events=api.ledger.latest_events(event['task_id']); previous=api.ledger.next_capsule_version(event['task_id']); api.ledger.save_capsule(build_capsule(event['task_id'],events,previous))
  api.ledger.ack_outbox(row['id'],'shadow_recorded'); completed.append(eid)
 projection=write_projection(api)
 return {'processed':len(completed),'event_ids':completed,'flags':{k:flags.get(k) for k in ('eventSliceShadow','capsuleShadow')},'projection':projection}
