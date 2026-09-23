"""Split mixed world/experience records into exact atomic siblings."""
from __future__ import annotations

import asyncio
from hashlib import sha256
import datetime as dt
import json
from pathlib import Path
import uuid

from observation_rebuild import atomic

BANK="personal-memory"
INSTANCE=Path.home()/'.pg0/instances/hindsight-embed-agentmemory/instance.json'


def split_plan(decision:dict)->dict:
    if decision.get('decision')!='split_required' or decision.get('actual_type') not in {'world','experience'}:raise ValueError('invalid_split_decision')
    original_type=decision['actual_type'];new_type='experience' if original_type=='world' else 'world'
    original_text=str(decision.get(original_type+'_text') or '').strip();new_text=str(decision.get(new_type+'_text') or '').strip()
    if not original_text or not new_text:raise ValueError('split_side_empty')
    new_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'guidance-v1-split:'+decision['id']+':'+new_type))
    return {'original_id':decision['id'],'original_type':original_type,'original_text':original_text,'new_id':new_id,'new_type':new_type,'new_text':new_text}


async def main(audit_path:str,output_dir:str):
    import asyncpg
    from sentence_transformers import SentenceTransformer
    audit=json.loads(Path(audit_path).read_text());decisions=[row for row in audit['results'] if row.get('decision')=='split_required'];plans=[];held=[]
    for decision in decisions:
        try:plans.append({**split_plan(decision),'text_sha256':decision['text_sha256'],'reason':decision.get('reason')})
        except Exception as error:held.append({'id':decision.get('id'),'reason':str(error)})
    cfg=json.loads(INSTANCE.read_text());root=Path(output_dir);root.mkdir(parents=True,exist_ok=True)
    db=await asyncpg.connect(user=cfg['username'],password=cfg['password'],database=cfg['database'],host='127.0.0.1',port=cfg['port'])
    try:
        rows=await db.fetch("SELECT * FROM memory_units WHERE bank_id=$1 AND id=ANY($2::uuid[])",BANK,[p['original_id'] for p in plans]);current={str(r['id']):dict(r) for r in rows}
        valid=[]
        for plan in plans:
            row=current.get(plan['original_id'])
            if not row or row['fact_type']!=plan['original_type'] or sha256(row['text'].encode()).hexdigest()!=plan['text_sha256']:
                held.append({'id':plan['original_id'],'reason':'current_revision_or_type_changed'});continue
            valid.append(plan)
        entity_rows=await db.fetch("SELECT unit_id::text,entity_id::text FROM unit_entities WHERE unit_id=ANY($1::uuid[])",[p['original_id'] for p in valid]) if valid else []
        entities={};[entities.setdefault(r['unit_id'],[]).append(r['entity_id']) for r in entity_rows]
        def serial(row):
            out={}
            for key,value in row.items():
                if hasattr(value,'isoformat'):value=value.isoformat()
                elif key=='embedding' and value is not None:value=str(value)
                elif isinstance(value,uuid.UUID):value=str(value)
                out[key]=value
            return out
        atomic(root/'before-splits.json',{'bank':BANK,'at':dt.datetime.now(dt.timezone.utc).isoformat(),'items':[{'row':serial(current[p['original_id']]),'entity_ids':entities.get(p['original_id'],[]),'new_id':p['new_id']} for p in valid]})
        model=SentenceTransformer('intfloat/multilingual-e5-small',local_files_only=True)
        texts=[text for p in valid for text in (p['original_text'],p['new_text'])];vectors=model.encode(['passage: '+text for text in texts],normalize_embeddings=True,show_progress_bar=False)
        inserted=[]
        async with db.transaction():
            for index,plan in enumerate(valid):
                row=current[plan['original_id']];meta=json.loads(row['metadata']) if isinstance(row['metadata'],str) else dict(row['metadata'] or {})
                group='split:'+plan['original_id'];original_meta={**meta,'guidance_v1_split_group':group,'guidance_v1_split_role':'original','guidance_v1_split_at':dt.datetime.now(dt.timezone.utc).isoformat(),'guidance_v1_split_reason':plan['reason']}
                new_meta={**meta,'guidance_v1_split_group':group,'guidance_v1_split_role':'sibling','guidance_v1_split_source_id':plan['original_id'],'guidance_v1_split_at':dt.datetime.now(dt.timezone.utc).isoformat(),'guidance_v1_split_reason':plan['reason']}
                ov='['+','.join(f'{float(x):.8f}' for x in vectors[index*2])+']';nv='['+','.join(f'{float(x):.8f}' for x in vectors[index*2+1])+']'
                await db.execute("UPDATE memory_units SET text=$1,embedding=$2::vector,fact_type=$3,metadata=$4::jsonb,search_vector=to_tsvector('simple',$1),search_vector_cjk_v1=NULL,consolidated_at=NULL,consolidation_failed_at=NULL,edited_at=now(),updated_at=now() WHERE bank_id=$5 AND id=$6::uuid",
                                 plan['original_text'],ov,plan['original_type'],json.dumps(original_meta,ensure_ascii=False),BANK,plan['original_id'])
                await db.execute("INSERT INTO memory_units(id,bank_id,document_id,text,embedding,context,event_date,occurred_start,occurred_end,mentioned_at,fact_type,metadata,created_at,updated_at,chunk_id,tags,proof_count,source_memory_ids,consolidated_at,observation_scopes,text_signals,search_vector,consolidation_failed_at,edited_at,search_vector_cjk_v1) VALUES($1::uuid,$2,$3,$4,$5::vector,$6,$7,$8,$9,$10,$11,$12::jsonb,now(),now(),$13,$14,$15,$16,NULL,NULL,$17,to_tsvector('simple',$4),NULL,now(),NULL) ON CONFLICT(id) DO NOTHING",
                                 plan['new_id'],BANK,row['document_id'],plan['new_text'],nv,row['context'],row['event_date'],row['occurred_start'],row['occurred_end'],row['mentioned_at'],plan['new_type'],json.dumps(new_meta,ensure_ascii=False),row['chunk_id'],row['tags'],row['proof_count'],row['source_memory_ids'],row['text_signals'])
                for entity_id in entities.get(plan['original_id'],[]):await db.execute("INSERT INTO unit_entities(unit_id,entity_id) VALUES($1::uuid,$2::uuid) ON CONFLICT DO NOTHING",plan['new_id'],entity_id)
                inserted.append(plan)
        ids=[p['original_id'] for p in inserted]+[p['new_id'] for p in inserted];rows=await db.fetch("SELECT id::text,text,fact_type FROM memory_units WHERE bank_id=$1 AND id=ANY($2::uuid[])",BANK,ids);got={r['id']:(r['text'],r['fact_type']) for r in rows}
        mismatches=[p['original_id'] for p in inserted if got.get(p['original_id'])!=(p['original_text'],p['original_type']) or got.get(p['new_id'])!=(p['new_text'],p['new_type'])]
        if mismatches:raise ValueError('split_readback_mismatch')
        report={'schema':'guidance.taxonomy-split.v1','at':dt.datetime.now(dt.timezone.utc).isoformat(),'requested':len(decisions),'split':len(inserted),'held':len(held),'new_records':len(inserted),'readback_mismatches':mismatches,'held_items':held,'rollback_source':str(root/'before-splits.json')}
        atomic(root/'split-report.json',report);print(json.dumps({k:report[k] for k in ('requested','split','held','new_records','readback_mismatches')},ensure_ascii=False))
    finally:await db.close()

if __name__=='__main__':
    import sys
    asyncio.run(main(*sys.argv[1:]))
