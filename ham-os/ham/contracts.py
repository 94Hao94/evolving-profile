from __future__ import annotations
import hashlib,json,uuid
from dataclasses import asdict,dataclass,field
from datetime import datetime,timezone
from typing import Any

EVENT_SCHEMA='ham.event.v1'; SLICE_SCHEMA='ham.event_slice.v1'; RECEIPT_VERSION='ham.receipt.v1'
ORIGINS={'user_request','ambient_context','system_instruction','assistant','tool_call','tool_result','file_change','memory_injection'}
EVENT_TYPES={'turn','tool','artifact','checkpoint','feedback'}

def utcnow()->str: return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def canonical(value:Any)->bytes: return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def digest(value:Any)->str: return hashlib.sha256(canonical(value)).hexdigest()

class ContractError(ValueError): pass
@dataclass(frozen=True)
class EventEnvelope:
    principal_id:str; agent_id:str; session_id:str; project_id:str; task_id:str; sequence:int
    origin_class:str; event_type:str; body_preview:str=''; body_ref:str|None=None; source_uri:str|None=None
    event_id:str=field(default_factory=lambda:str(uuid.uuid4())); idempotency_key:str|None=None
    occurred_at:str=field(default_factory=utcnow); recorded_at:str=field(default_factory=utcnow)
    parent_event_ids:list[str]=field(default_factory=list); injected_memory_ids:list[str]=field(default_factory=list)
    visibility_scope:str='principal_shared'; status:str='persisted'; schema:str=EVENT_SCHEMA
    def payload(self)->dict[str,Any]:
        p=asdict(self); p['idempotency_key']=self.idempotency_key or digest({k:v for k,v in p.items() if k not in {'idempotency_key','recorded_at','status'}}); return p

def validate_event(payload:dict[str,Any])->dict[str,Any]:
    required={'schema','event_id','idempotency_key','principal_id','agent_id','session_id','project_id','task_id','sequence','origin_class','event_type','occurred_at','recorded_at','body_preview','parent_event_ids','injected_memory_ids','visibility_scope','status'}
    missing=required-set(payload)
    if missing: raise ContractError(f'missing:{sorted(missing)}')
    if payload['schema']!=EVENT_SCHEMA: raise ContractError('unsupported_event_schema')
    if payload['origin_class'] not in ORIGINS: raise ContractError('invalid_origin_class')
    if payload['event_type'] not in EVENT_TYPES: raise ContractError('invalid_event_type')
    if not all(isinstance(payload[x],str) and payload[x] for x in ('event_id','idempotency_key','principal_id','agent_id','session_id','project_id','task_id')): raise ContractError('invalid_identity')
    if not isinstance(payload['sequence'],int) or payload['sequence']<0: raise ContractError('invalid_sequence')
    if len(payload['body_preview'])>4096: raise ContractError('preview_too_large')
    if payload['origin_class']=='memory_injection' and not payload['injected_memory_ids']: raise ContractError('missing_injected_memory_lineage')
    return payload

def receipt(*,request_id:str|None=None,execution_id:str|None=None,persistence='not_applicable',execution='complete',coverage='not_required',continuation='not_needed',error_code=None,retryable=False,**extra):
    return {'request_id':request_id or str(uuid.uuid4()),'execution_id':execution_id or str(uuid.uuid4()),'transport_status':'ok','persistence_status':persistence,'execution_status':execution,'coverage_status':coverage,'continuation_status':continuation,'retryable':retryable,'error_code':error_code,'receipt_version':RECEIPT_VERSION,**extra}
