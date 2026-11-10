#!/usr/bin/env python3
"""A/B/C isolation protocol smoke test; uses only temporary state and no hidden content."""
from __future__ import annotations
import json,os,sqlite3,tempfile
from pathlib import Path
from ham.api import Api
from ham.contracts import EventEnvelope

def counts(path:Path):
 c=sqlite3.connect(path); return {t:c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('events','outbox','task_capsules')}
def main():
 production=Path.home()/'.hindsight/memory-os/state.sqlite3'; before=counts(production)
 result={'schema':'ham.isolation.smoke.v1','modes':{},'repetitions':3,'production_before':before}
 with tempfile.TemporaryDirectory(prefix='ham-isolation-') as td:
  root=Path(td); contract=root/'contract.json'; contract.write_text(json.dumps({'memoryOS':{'enabled':True,'ledgerDualWrite':True,'needGraphShadow':True,'dynamicPackBudget':True,'generation':'isolation-smoke','phase':'5'}}))
  for mode in ('native_only','ham_os_only','combined'):
   runs=[]
   for n in range(3):
    old=os.environ.get('CODEX_HOME'); os.environ['CODEX_HOME']=str(root/f'codex-{mode}-{n}')
    api=Api(root/f'state-{mode}-{n}',contract)
    payload=EventEnvelope(principal_id='isolation',agent_id='codex',session_id=f's{n}',project_id='p',task_id='t',sequence=1,origin_class='user_request',event_type='turn',body_preview='isolation evidence').payload()
    if mode!='native_only': api.handle('POST','/v2/memory-os/events',json.dumps(payload).encode(),{'Idempotency-Key':payload['idempotency_key']})
    status,value=api.handle('POST','/v2/memory-os/query',json.dumps({'task_id':'t','user_request':'continue isolated task','remaining_context_tokens':128}).encode(),{})
    runs.append({'http':status,'execution':value.get('execution_status'),'evidence':value.get('progress',{}).get('available_evidence_count')})
    if old is None: os.environ.pop('CODEX_HOME',None)
    else: os.environ['CODEX_HOME']=old
   result['modes'][mode]=runs
 result['production_after']=counts(production); result['pollution_free']=before==result['production_after']
 print(json.dumps(result,ensure_ascii=False,sort_keys=True)); return 0 if result['pollution_free'] and all(r['http']==200 for rows in result['modes'].values() for r in rows) else 1
if __name__=='__main__': raise SystemExit(main())
