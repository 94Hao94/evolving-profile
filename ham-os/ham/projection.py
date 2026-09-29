from __future__ import annotations
import json
from pathlib import Path
from .contracts import utcnow
def write_projection(api):
 with api.ledger.lock:
  events=api.ledger.conn.execute('SELECT count(*) FROM events').fetchone()[0]
  capsules=api.ledger.conn.execute('SELECT count(*) FROM task_capsules').fetchone()[0]
  slices=api.ledger.conn.execute('SELECT count(*) FROM event_slices').fetchone()[0]
 value={'schema':'ham.status_projection.v1','computed_at':utcnow(),'generation':api.flags().get('generation'),'health':api.ledger.outbox_health(),'raw_event_coverage':events,'task_capsules':capsules,'derived_provenance_coverage':slices,'adapter_flags':{k:v for k,v in api.flags().items() if k.startswith('adapterV2') or k=='adapterAuthEnforce'},'spec_version':api.flags().get('specVersion')}
 target=api.state_root/'status-projection.json'; temp=target.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True));temp.replace(target);return value
