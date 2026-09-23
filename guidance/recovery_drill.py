"""Commit-and-restore one real taxonomy change, then return production to new state."""
from __future__ import annotations
import asyncio,datetime as dt,json
from pathlib import Path
import asyncpg
from observation_rebuild import atomic
INSTANCE=Path.home()/'.pg0/instances/hindsight-embed-agentmemory/instance.json';BANK='personal-memory'
async def main(before_path,output_path):
 before=json.loads(Path(before_path).read_text())['items'];cfg=json.loads(INSTANCE.read_text());db=await asyncpg.connect(user=cfg['username'],password=cfg['password'],database=cfg['database'],host='127.0.0.1',port=cfg['port'])
 try:
  target=None
  for item in before:
   current=await db.fetchrow('SELECT fact_type FROM memory_units WHERE bank_id=$1 AND id=$2::uuid',BANK,item['id'])
   if current and current['fact_type']!=item['fact_type']:target=(item,current['fact_type']);break
  if not target:raise ValueError('no_changed_record_for_recovery_drill')
  item,new_type=target
  await db.execute('UPDATE memory_units SET fact_type=$1,updated_at=now() WHERE bank_id=$2 AND id=$3::uuid',item['fact_type'],BANK,item['id'])
  restored=await db.fetchval('SELECT fact_type FROM memory_units WHERE bank_id=$1 AND id=$2::uuid',BANK,item['id'])
  await db.execute('UPDATE memory_units SET fact_type=$1,updated_at=now() WHERE bank_id=$2 AND id=$3::uuid',new_type,BANK,item['id'])
  final=await db.fetchval('SELECT fact_type FROM memory_units WHERE bank_id=$1 AND id=$2::uuid',BANK,item['id'])
  report={'schema':'guidance.recovery-drill.v1','at':dt.datetime.now(dt.timezone.utc).isoformat(),'memory_id':item['id'],'old_type':item['fact_type'],'new_type':new_type,'restore_readback':restored,'final_readback':final,'passed':restored==item['fact_type'] and final==new_type,'production_state_restored_to_new_version':final==new_type}
  atomic(Path(output_path),report);print(json.dumps(report,ensure_ascii=False))
 finally:await db.close()
if __name__=='__main__':
 import sys;asyncio.run(main(*sys.argv[1:]))
