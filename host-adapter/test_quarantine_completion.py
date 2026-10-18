import hashlib
import json

import pytest

from lib.retention_queue import RetentionQueue


def signature(row):
    return hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def prepare(tmp_path):
    q=RetentionQueue(tmp_path/'queue.json')
    q.capture('s',1,'bank-a','project-a','必须保留的原文',{},captured_at='2020-01-01T00:00:00Z')
    row=q.snapshot()['items'][0]
    q.mark_submitted('batch-a','op-a',item_ids=[row['id']])
    q.quarantine_operation('op-a','retention_retry_exhausted:failed')
    q.capture('other',1,'bank-b','project-b','其他记忆库原文',{})
    row=q.snapshot()['items'][0]
    return q,{row['id']:signature(row)}


def test_confirmed_completion_removes_only_bound_unchanged_quarantine(tmp_path):
    q,expected=prepare(tmp_path)
    receipt={'status':'completed','operation_id':'op-a'}
    assert q.reconcile_quarantined_completion('bank-a','op-a',receipt,expected)==1
    assert [r['content'] for r in q.snapshot()['items']]==['其他记忆库原文']
    assert q.reconcile_quarantined_completion('bank-a','op-a',receipt,expected)==0


def test_foreign_bank_duplicate_id_is_not_deleted(tmp_path):
    q,expected=prepare(tmp_path)
    with q._locked():
        state=q._read()
        foreign={**state['items'][0],'bank_id':'foreign-bank','content':'另一记忆库的同ID记录'}
        state['items'].append(foreign);q._write(state)
    assert q.reconcile_quarantined_completion('bank-a','op-a',{'status':'completed','operation_id':'op-a'},expected)==1
    assert any(r['bank_id']=='foreign-bank' for r in q.snapshot()['items'])


@pytest.mark.parametrize('case',['pending','wrong_id','wrong_bank','changed_source','incomplete_snapshot'])
def test_unverified_or_changed_quarantine_is_never_deleted(tmp_path,case):
    q,expected=prepare(tmp_path)
    receipt={'status':'completed','operation_id':'op-a'}
    bank='bank-a'
    if case=='pending':receipt['status']='processing'
    if case=='wrong_id':receipt['operation_id']='other'
    if case=='wrong_bank':bank='bank-b'
    if case=='incomplete_snapshot':expected={}
    if case=='changed_source':
        with q._locked():
            state=q._read();state['items'][0]['content']='后来发生变化的原文';q._write(state)
    before=q.path.read_bytes()
    with pytest.raises(ValueError):q.reconcile_quarantined_completion(bank,'op-a',receipt,expected)
    assert q.path.read_bytes()==before
