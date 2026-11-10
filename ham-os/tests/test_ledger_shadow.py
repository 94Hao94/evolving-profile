from pathlib import Path
import pytest
from ham.contracts import EventEnvelope,ContractError
from ham.storage import Ledger,IdempotencyConflict,TABLES
from ham.events import deterministic_slice
from ham.capsules import build_capsule

def event(seq=1,**kw):
    args=dict(principal_id='p',agent_id='codex',session_id='s',project_id='proj',task_id='task',sequence=seq,origin_class='user_request',event_type='turn',body_preview='do work'); args.update(kw); return EventEnvelope(**args).payload()
def test_schema_contains_spec_tables(tmp_path):
 ledger=Ledger(tmp_path/'state.sqlite3'); names={r[0] for r in ledger.conn.execute("select name from sqlite_master where type='table'")}; assert set(TABLES)<=names
def test_append_is_durable_idempotent_and_conflict_is_audit_safe(tmp_path):
 ledger=Ledger(tmp_path/'state.sqlite3'); e=event(); first=ledger.append_event(e); replay=ledger.append_event(e); assert first['durable'] and not first['idempotent_replay']; assert replay['idempotent_replay']
 altered=dict(e); altered['body_preview']='changed'
 with pytest.raises(IdempotencyConflict): ledger.append_event(altered)
 assert len(ledger.latest_events('task'))==1 and ledger.outbox_health()['pending']==1
def test_event_slice_is_deterministic_and_preserves_unknowns(tmp_path):
 e=event(); s1=deterministic_slice(e,0); s2=deterministic_slice(e,0); assert s1['slice_id']==s2['slice_id']; assert s1['action']=='' and s1['validation_status']=='unknown'
def test_capsule_uses_evidence_not_inferred_objective(tmp_path):
 e=event(); capsule=build_capsule('task',[e]); assert capsule['objective']['value']==''; assert capsule['current_state']['evidence_ids']==[e['event_id']]
def test_memory_injection_requires_lineage(tmp_path):
 p=event(origin_class='memory_injection')
 with pytest.raises(ContractError): Ledger(tmp_path/'ham-unused.sqlite3').append_event(p)
def test_threaded_receipts_are_serialized(tmp_path):
    import threading
    ledger=Ledger(tmp_path/'state.sqlite3'); outcomes=[]
    def write(n):
        outcomes.append(ledger.append_event(event(n)))
    threads=[threading.Thread(target=write,args=(n,)) for n in range(1,21)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert len(outcomes)==20 and len(ledger.latest_events('task'))==20
def test_worker_acks_outbox_without_upstream(tmp_path):
    from ham.api import Api
    from ham.worker import process
    import json
    contract=tmp_path/'contract.json'; contract.write_text(json.dumps({'memoryOS':{'enabled':True,'ledgerDualWrite':True,'eventSliceShadow':False,'capsuleShadow':False,'generation':'g','phase':'1'}}))
    api=Api(tmp_path/'state',contract); api.ledger.append_event(event()); got=process(api); assert got['processed']==1 and api.ledger.outbox_health()['pending']==0
def test_handoff_migration_is_provisional_and_down_read_safe(tmp_path):
    from ham.migrations import migrate
    import json
    source=tmp_path/'handoffs.json'; source.write_text(json.dumps({'records':[{'id':'x','session_id':'s','project':'p','current_goal':'goal','latest_result':'done','recent_decisions':['d'],'open_items':['n'],'references':{'paths':['/a']}}]}))
    ledger=Ledger(tmp_path/'state.sqlite3'); report=migrate(ledger,source,False); assert report['capsules']==1 and json.loads(source.read_text())['records'][0]['id']=='x'
