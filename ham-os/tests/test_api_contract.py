import json
from pathlib import Path
from ham.api import Api
from ham.contracts import EventEnvelope

def make(tmp_path,enabled=True):
 c=tmp_path/'contract.json'; c.write_text(json.dumps({'memoryOS':{'enabled':enabled,'phase':'1','needGraphShadow':True,'generation':'g','specVersion':'1.0-review.4'}})); return Api(tmp_path/'state',c)
def event(): return EventEnvelope(principal_id='p',agent_id='codex',session_id='s',project_id='p',task_id='t',sequence=1,origin_class='user_request',event_type='turn',body_preview='hello').payload()
def test_capabilities_available_before_enable(tmp_path):
 s,v=make(tmp_path,False).handle('GET','/v2/memory-os/capabilities',b'',{}); assert s==200 and v['enabled'] is False

def test_api_resolves_migrated_evolving_profile_root(monkeypatch, tmp_path):
    home = tmp_path / 'home'
    contract = home / '.evolving-profile' / 'memory-contract-v5.json'
    contract.parent.mkdir(parents=True)
    contract.write_text(json.dumps({'memoryOS': {'enabled': True, 'generation': 'migrated'}}))
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.delenv('HAM_MEMORY_CONTRACT', raising=False)
    monkeypatch.delenv('HAM_OS_STATE_ROOT', raising=False)

    api = Api()

    assert api.flags()['enabled'] is True
    assert api.contract_path == contract
    assert api.state_root == home / '.evolving-profile' / 'memory-os'
def test_event_idempotency_and_query_read_your_writes(tmp_path):
 a=make(tmp_path); p=event(); s,v=a.handle('POST','/v2/memory-os/events',json.dumps(p).encode(),{'Idempotency-Key':p['idempotency_key']}); assert s==200 and v['persistence_status']=='durable'
 s,v=a.handle('POST','/v2/memory-os/query',json.dumps({'task_id':'t','user_request':'继续这个任务'}).encode(),{}); assert s==200 and v['progress']['available_evidence_count']==1
def test_conflict_and_disabled_use_required_statuses(tmp_path):
 a=make(tmp_path); p=event(); a.handle('POST','/v2/memory-os/events',json.dumps(p).encode(),{'Idempotency-Key':p['idempotency_key']}); p['body_preview']='other'; s,v=a.handle('POST','/v2/memory-os/events',json.dumps(p).encode(),{'Idempotency-Key':p['idempotency_key']}); assert (s,v['error_code'])==(409,'idempotency_conflict')
 s,v=make(tmp_path,False).handle('POST','/v2/memory-os/events',b'{}',{}); assert (s,v['error_code'])==(422,'unsupported_semantics')
def test_progress_is_persisted_and_monotonic(tmp_path):
 a=make(tmp_path); s,v=a.handle('POST','/v2/memory-os/query',json.dumps({'execution_id':'e','task_id':'missing','user_request':'why'}).encode(),{}); s,v=a.handle('GET','/v2/memory-os/executions/e',b'',{}); assert v['progress_version']==1 and v['execution_status']=='complete'

def test_expansion_and_dynamic_budget(tmp_path):
 c=tmp_path/'contract.json'; c.write_text(json.dumps({'memoryOS':{'enabled':True,'phase':'4','needGraphShadow':True,'dynamicPackBudget':True,'generation':'g'}})); a=Api(tmp_path/'state',c)
 for n in range(3):
  p=EventEnvelope(principal_id='p',agent_id='codex',session_id='s',project_id='p',task_id='t',sequence=n+1,origin_class='user_request',event_type='turn',body_preview='x'*300).payload(); a.handle('POST','/v2/memory-os/events',json.dumps(p).encode(),{'Idempotency-Key':p['idempotency_key']})
 s,v=a.handle('POST','/v2/memory-os/query',json.dumps({'task_id':'t','user_request':'continue','remaining_context_tokens':128}).encode(),{}); assert s==200 and v['memory_pack']['token_budget']==128
 h=v['memory_pack']['expansion_handle']; assert h
 s,v=a.handle('POST','/v2/memory-os/expand',json.dumps({'expansion_handle':h,'limit':2}).encode(),{}); assert s==200 and len(v['memory_pack']['items'])==2

def test_adapter_auth_registry_and_nonce_replay(tmp_path):
 import hmac,hashlib,time
 c=tmp_path/'contract.json'; c.write_text(json.dumps({'memoryOS':{'enabled':True,'phase':'4','needGraphShadow':True,'adapterAuthEnforce':True,'generation':'g'}})); a=Api(tmp_path/'state',c)
 a.auth.path.write_text(json.dumps({'adapters':{'codex':{'enabled':True,'hmac_key':'test-key'}}}))
 p=event(); body=json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(',',':')); nonce=f'{time.time()}:n'
 sig=hmac.new(b'test-key',(nonce+'\n'+body).encode(),hashlib.sha256).hexdigest(); headers={'Idempotency-Key':p['idempotency_key'],'X-HAM-Adapter':'codex','X-HAM-Nonce':nonce,'X-HAM-Signature':sig}
 s,v=a.handle('POST','/v2/memory-os/events',json.dumps(p).encode(),headers); assert s==200
 s,v=a.handle('POST','/v2/memory-os/events',json.dumps(p).encode(),headers); assert (s,v['error_code'])==(401,'adapter_unverified')

def test_concurrent_queries_share_locked_ledger(tmp_path):
 from concurrent.futures import ThreadPoolExecutor
 a=make(tmp_path); p=event(); a.handle('POST','/v2/memory-os/events',json.dumps(p).encode(),{'Idempotency-Key':p['idempotency_key']})
 def query(n): return a.handle('POST','/v2/memory-os/query',json.dumps({'execution_id':f'e{n}','task_id':'t','user_request':'continue'}).encode(),{})[0]
 with ThreadPoolExecutor(max_workers=12) as pool: assert set(pool.map(query,range(64)))=={200}


def test_mer_query_returns_contract_claim_receipt_and_never_claims_hook_injection(tmp_path):
 c=tmp_path/'contract.json'; c.write_text(json.dumps({'memoryOS':{'enabled':True,'phase':'bplus','needGraphShadow':True,'dynamicPackBudget':True,'memoryEvidenceRuntime':True,'generation':'g'}}))
 a=Api(tmp_path/'state',c)
 for n,text in enumerate(('官方 Hindsight 初始版本','Hooks 和 Controller 阶段','当前 Agent Memory OS 阶段')):
  p=EventEnvelope(principal_id='p',agent_id='codex',session_id='s',project_id='p',task_id='t',sequence=n+1,origin_class='user_request',event_type='turn',body_preview=text).payload()
  a.handle('POST','/v2/memory-os/events',json.dumps(p).encode(),{'Idempotency-Key':p['idempotency_key']})
 s,v=a.handle('POST','/v2/memory-os/query',json.dumps({'execution_id':'mer-e1','task_id':'t','user_request':'Hindsight 从最开始官方到现在经历多少次变迁','remaining_context_tokens':256}).encode(),{})
 assert s==200
 assert v['query_contract']['workload']=='evolution'
 assert v['claim_receipt']['actual_hook_injected_claim_ids']==[]
 assert v['memory_pack']['schema']=='ham.claim_pack.v1'
 assert v['memory_pack']['coverage']['status']=='complete'
 s,progress=a.handle('GET','/v2/memory-os/executions/mer-e1',b'',{})
 assert progress['query_contract']['execution_id']=='mer-e1'


def test_mer_expand_resumes_execution_and_returns_claim_pack(tmp_path):
 c=tmp_path/'contract.json'; c.write_text(json.dumps({'memoryOS':{'enabled':True,'phase':'bplus','needGraphShadow':True,'dynamicPackBudget':True,'memoryEvidenceRuntime':True,'generation':'g'}}))
 a=Api(tmp_path/'state',c)
 p=event(); a.handle('POST','/v2/memory-os/events',json.dumps(p).encode(),{'Idempotency-Key':p['idempotency_key']})
 s,v=a.handle('POST','/v2/memory-os/query',json.dumps({'execution_id':'mer-expand','task_id':'t','user_request':'Hindsight 从最开始官方到现在经历多少次变迁','remaining_context_tokens':128}).encode(),{})
 assert s==200 and v['memory_pack']['expansion_handle']
 handle=v['memory_pack']['expansion_handle']
 s,v=a.handle('POST','/v2/memory-os/expand',json.dumps({'execution_id':'mer-expand','expansion_handle':handle,'limit':2}).encode(),{})
 assert s==200
 assert v['execution_id']=='mer-expand'
 assert v['memory_pack']['schema']=='ham.claim_pack.v1'
 assert 'claims' in v['memory_pack']
 assert v['memory_pack']['claims']
 assert v['memory_pack']['expansion_handle'] is None
