from __future__ import annotations
import hashlib,json,os,uuid
from .auth import AdapterAuth
from pathlib import Path
from typing import Any
from .contracts import ContractError,EventEnvelope,receipt,utcnow
from .storage import IdempotencyConflict,Ledger
from .planner import need_graph
from .coverage import receipt as coverage_receipt
from .packs import build_pack
from .evidence_runtime import EvidenceCandidate, QueryContract, ClaimLedger, pack_claims

ROOT=Path(__file__).resolve().parents[1]
SCHEMA_ROOT=ROOT/'schemas'
class Api:
 def __init__(self,state_root:Path|None=None,contract_path:Path|None=None):
  self.state_root=Path(state_root or os.environ.get('HAM_OS_STATE_ROOT') or Path.home()/'.hindsight/memory-os'); self.state_root.mkdir(parents=True,exist_ok=True)
  self.contract_path=Path(contract_path or Path.home()/'.hindsight/memory-contract-v5.json'); self.ledger=Ledger(self.state_root/'state.sqlite3'); self.auth=AdapterAuth(self.state_root/'adapter-registry.json')
 def contract(self): return json.loads(self.contract_path.read_text())
 def flags(self): return self.contract().get('memoryOS') or {}
 def response(self,status:int,value:dict):
  value.setdefault('schema_version','ham.api.v2'); value.setdefault('server_generation',self.flags().get('generation','unknown')); value.setdefault('policy_hash',hashlib.sha256(self.contract_path.read_bytes()).hexdigest()); value.setdefault('computed_at',utcnow()); value.setdefault('trace_id',str(uuid.uuid4())); return status,value
 def capabilities(self):
  f=self.flags(); return self.response(200,{'schema':'ham.capabilities.v1','enabled':bool(f.get('enabled')),'phase':f.get('phase'),'schema_uris':['schemas/api/query.schema.json','schemas/events/event-envelope.schema.json','schemas/receipts/execution-progress.schema.json'],'max_payload_bytes':1048576,'page_limits':{'default':50,'max':200},'status_enums':{'execution':['running','partial','complete','failed','noop','stalled'],'coverage':['complete','incomplete','unknown','not_required']},'adapter_contract':'ham.adapter.v1'})
 def _error(self,status,code,**extra): return self.response(status,receipt(execution='failed',coverage='unknown',continuation='not_needed',error_code=code,retryable=code in {'generation_skew','quota_circuit_open','upstream_unavailable','storage_pressure'},**extra))
 def handle(self,method:str,path:str,body:bytes,headers:dict[str,str]):
  path=path.split('?',1)[0]
  if path=='/v2/memory-os/capabilities' and method=='GET': return self.capabilities()
  if path=='/v2/memory-os/health' and method=='GET': return self.response(200,{'status':'healthy','ledger':self.ledger.outbox_health(),'flags':self.flags()})
  if path.startswith('/v2/memory-os/executions/') and method=='GET':
   eid=path.rsplit('/',1)[1]; value=self.ledger.get_execution(eid)
   return self.response(200,value if value else {'schema':'ham.execution_progress.v1','execution_id':eid,'progress_version':0,'execution_status':'noop','current_stage':'done','facets':{'completed':[],'running':[],'waiting':[],'failed':[]},'coverage_delta':{'covered':[],'missing':[],'conflicted':[]},'available_evidence_count':0,'next_best_query':None,'quota_state':'closed','updated_at':utcnow(),'foreground_injection_closed':True})
  if path.startswith('/v2/memory-os/tasks/') and method=='GET':
   tid=path.rsplit('/',1)[1]; return self.response(200,{'task_id':tid,'capsule':self.ledger.latest_capsule(tid)})
  if not self.flags().get('enabled'): return self._error(422,'unsupported_semantics')
  if len(body)>1048576: return self._error(413,'payload_too_large')
  try: value=json.loads(body.decode() or '{}')
  except Exception: return self._error(400,'invalid_envelope')
  if path=='/v2/memory-os/events' and method=='POST': return self.event(value,headers)
  if path=='/v2/memory-os/query' and method=='POST': return self.query(value)
  if path=='/v2/memory-os/expand' and method=='POST': return self.expand(value)
  if path=='/v2/memory-os/feedback' and method=='POST': return self.feedback(value)
  return self._error(404,'not_found')
 def event(self,value,headers):
  try:
   if self.flags().get('adapterAuthEnforce'):
    ok,reason=self.auth.verify(headers,body=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    if not ok: return self._error(401,'adapter_unverified',auth_reason=reason)
   if 'Idempotency-Key' not in headers and 'idempotency-key' not in headers: return self._error(400,'invalid_envelope')
   value['idempotency_key']=headers.get('Idempotency-Key') or headers.get('idempotency-key'); r=self.ledger.append_event(value)
   return self.response(200,receipt(persistence='durable',execution='complete',coverage='not_required',event_id=r['event_id'],durable=True,idempotent_replay=r['idempotent_replay'],durable_elapsed_ms=r['elapsed_ms']))
  except IdempotencyConflict: return self._error(409,'idempotency_conflict')
  except ContractError: return self._error(400,'invalid_envelope')
 def query(self,v):
  if self.flags().get('memoryEvidenceRuntime'):
   return self._mer_query(v)
  if not self.flags().get('needGraphShadow'): return self._error(422,'unsupported_semantics')
  eid=str(v.get('execution_id') or uuid.uuid4()); tid=str(v.get('task_id') or ''); graph=need_graph(str(v.get('user_request') or ''),str(v.get('workload_class_hint') or 'ordinary_semantic')); events=self.ledger.latest_events(tid) if tid else []
  cover=coverage_receipt(graph['facets'],['task_capsule'] if events else [])
  progress={'schema':'ham.execution_progress.v1','execution_id':eid,'progress_version':1,'execution_status':'complete','current_stage':'done','facets':{'completed':['ledger'] if events else [],'running':[],'waiting':[],'failed':[]},'coverage_delta':{'covered':cover['covered_dimensions'],'missing':cover['missing_dimensions'],'conflicted':[]},'available_evidence_count':len(events),'next_best_query':None,'quota_state':'closed','updated_at':utcnow(),'foreground_injection_closed':True}
  self.ledger.save_execution(eid,progress)
  requested=int(v.get('remaining_context_tokens') or 1200)
  budget=max(128,min(8000,requested if self.flags().get('dynamicPackBudget') else 1200))
  pack=build_pack([{'id':e['event_id'],'text':e['body_preview']} for e in events],budget)
  if pack.get('expansion_handle'):
   handle=str(uuid.uuid4()); pack['expansion_handle']=handle; self.ledger.save_pack(handle,{'execution_id':eid,'items':[{'id':e['event_id'],'text':e['body_preview']} for e in events],'created_at':utcnow()})
  return self.response(200,receipt(execution_id=eid,execution='complete',coverage=cover['coverage_status'],continuation='not_needed',need_graph=graph,memory_pack=pack,progress=progress))

 def _mer_candidate(self,event:dict[str,Any])->EvidenceCandidate:
  text=str(event.get('body_preview') or '')
  lowered=text.casefold()
  if '官方' in text or '初始' in text or '最初' in text:
   stage='origin'
  elif 'hook' in lowered or 'controller' in lowered:
   stage='hooks_controller'
  elif '当前' in text or 'agent memory os' in lowered:
   stage='current'
  elif '图谱' in text or '星座' in text:
   stage='graph_constellation'
  else:
   stage=None
  return EvidenceCandidate(
   record_id=str(event['event_id']), text=text, channel='task_event', stage=stage,
   authority=0.9 if stage in {'origin','current'} else 0.7,
   tokens=max(1,len(text)//2), occurred_at=event.get('occurred_at'), source_uri=event.get('source_uri'),
  )

 def _mer_contract_payload(self,contract:QueryContract)->dict[str,Any]:
  return {
   'schema':'ham.query_contract.v1','execution_id':contract.execution_id,'request':contract.request,
   'workload':contract.workload,'required_slots':list(contract.required_slots),
   'canonical_entities':list(contract.canonical_entities),'allow_historical':contract.allow_historical,
   'required_relation_closure':contract.required_relation_closure,
  }

 def _mer_query(self,v:dict[str,Any]):
  if not self.flags().get('needGraphShadow'): return self._error(422,'unsupported_semantics')
  eid=str(v.get('execution_id') or uuid.uuid4())
  contract=QueryContract.from_request(str(v.get('user_request') or ''),execution_id=eid)
  task_id=str(v.get('task_id') or '')
  ledger=ClaimLedger(contract)
  events=self.ledger.latest_events(task_id,limit=200) if task_id else []
  for event in reversed(events): ledger.add(self._mer_candidate(event))
  requested=int(v.get('remaining_context_tokens') or 1200)
  budget=max(128,min(8000,requested if self.flags().get('dynamicPackBudget') else 1200))
  pack=pack_claims(ledger,budget)
  coverage=ledger.coverage()
  receipt_payload={
   'schema':'ham.claim_receipt.v1','execution_id':eid,
   'candidate_record_count':len(events),'distinct_claim_count':len(ledger.claims()),
   'admitted_claim_ids':[claim['claim_key'] for claim in pack['claims']],
   'actual_hook_injected_claim_ids':[],
   'same_turn_tool_delivered_claim_ids':[],
   'rejected_claims':[],
   'background_claim_ids':[],
  }
  progress={
   'schema':'ham.execution_progress.v2','execution_id':eid,'progress_version':1,
   'execution_status':'complete' if coverage.status=='complete' else 'partial','current_stage':'pack_ready',
   'facets':{'completed':['task_event'],'running':[],'waiting':[],'failed':[]},
   'coverage_delta':{'covered':list(coverage.covered_slots),'missing':list(coverage.missing_slots),'conflicted':[]},
   'available_evidence_count':len(events),'next_best_query':None if coverage.status=='complete' else 'expand_required_slots',
   'quota_state':'closed','updated_at':utcnow(),'foreground_injection_closed':False,
   'query_contract':self._mer_contract_payload(contract),'claim_receipt':receipt_payload,
  }
  self.ledger.save_execution(eid,progress)
  if pack.get('expansion_handle'):
   self.ledger.save_pack(str(pack['expansion_handle']),{
    'execution_id':eid,'query_contract':self._mer_contract_payload(contract),
    'claims':pack['claims'],'coverage':pack['coverage'],'created_at':utcnow(),
   })
  return self.response(200,receipt(
   execution_id=eid,execution=progress['execution_status'],coverage=coverage.status,
   continuation='not_needed' if coverage.status=='complete' else 'expand_available',
   query_contract=self._mer_contract_payload(contract),claim_receipt=receipt_payload,
   memory_pack=pack,progress=progress,
  ))
 def expand(self,v):
  handle=str(v.get('expansion_handle') or ''); saved=self.ledger.get_pack(handle) if handle else None
  if not saved: return self.response(410,receipt(execution='noop',coverage='unknown',error_code='handle_expired'))
  limit=max(1,min(50,int(v.get('limit') or 10))); return self.response(200,receipt(execution='complete',coverage='not_required',continuation='not_needed',memory_pack={'schema':'ham.memory_pack.v1','items':saved['items'][:limit],'expansion_handle':None}))
 def feedback(self,v):
  fid=str(uuid.uuid4()); record={'schema':'ham.feedback.v1','mode':'audit_only','payload':v,'received_at':utcnow()}; self.ledger.save_feedback(fid,record); return self.response(200,receipt(execution='complete',coverage='not_required',feedback_id=fid,feedback_mode='audit_only'))
