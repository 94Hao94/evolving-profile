import copy

from lib.scenario_coverage_incremental import process_coverage_job,invalidate_dependents
from test_scenario_source_codec import SID,source


def job():
    return {'session_id':SID,'bank_id':'b','project_key':'explicit-project','attempts':1,'status':'waiting_source',
        'permission':{'allowed':True,'version':'p1'}}


def test_shadow_builds_structure_without_provider_or_publish_or_attempt_reset(tmp_path):
    root,_,_=source(tmp_path);calls=[];j=job()
    result=process_coverage_job(j,root,{},store_root=tmp_path/'state',provider=lambda p:calls.append(p))
    assert result['status']=='global_pending' and result['source_manifest_complete'] is True
    assert result['model_calls']==0 and calls==[] and result['published'] is False
    assert j['attempts']==1 and result['semantic_review_status']=='not_reviewed'
    again=process_coverage_job(j,root,{},store_root=tmp_path/'state',provider=lambda p:calls.append(p))
    assert again['snapshot_id']==result['snapshot_id'] and again['generation']==result['generation']


def test_protected_unknown_scope_and_permission_stop_before_read(tmp_path):
    root,_,_=source(tmp_path)
    for patch in [{'status':'protected'},{'bank_id':None},{'project_key':None},{'permission':{'allowed':False,'version':'p1'}}]:
        result=process_coverage_job({**job(),**patch},root,{},store_root=tmp_path/'state')
        assert result['status']=='unavailable' and result['model_calls']==0


def test_bounded_resume_and_changed_source_invalidate_global_not_old_attempts(tmp_path):
    root,path,_=source(tmp_path,text='不要删🙂。'*300)
    result=process_coverage_job(job(),root,{'limits':{'output_bytes':256,'input_bytes':256}},store_root=tmp_path/'state',max_leases=1)
    assert result['status']=='partial' and result['read_bytes']<=256
    newer=process_coverage_job(job(),root,{},store_root=tmp_path/'state')
    assert newer['source_manifest_complete'] is True
    assert newer['replayed_bytes']>=result['logical_offset']
    path.write_bytes(path.read_bytes()+b'{}\n')
    changed=process_coverage_job(job(),root,{},store_root=tmp_path/'state')
    assert changed['snapshot_id']!=newer['snapshot_id'] and changed['attempts']==1
    invalid=invalidate_dependents({'units':[{'unit_id':'old'}]}, {'units':[{'unit_id':'new'}]})
    assert invalid['global_review_invalidated'] is True and set(invalid['changed_units'])=={'old','new'}


def test_existing_worker_exposes_scoped_shadow_without_claiming_parent_job(tmp_path):
    from lib.context_incremental import ContextIncremental
    root,_,_=source(tmp_path)
    worker=ContextIncremental(tmp_path/'state',root,bank_id='b')
    worker.discover()
    before=worker.progress()
    result=worker.process_coverage(SID,{})
    assert result['model_calls']==0
    assert worker.progress()['succeeded']==before['succeeded']


def test_explicit_source_no_memory_write_blocks_new_semantic_inventory(tmp_path):
    root,_,_=source(tmp_path,text='本会话不要写入记忆。只回答当前问题。')
    result=process_coverage_job(job(),root,{},store_root=tmp_path/'state')
    assert result['status']=='unavailable' and result['reason']=='source_knowledge_write_prohibited'
    assert not (tmp_path/'state/inventories'/f'{SID}.json').exists()


def test_append_reuses_unchanged_partition_drafts_not_semantic_acceptance(tmp_path):
    root,path,_=source(tmp_path,text='保持原文🙂。'*1800);state=tmp_path/'state'
    first=process_coverage_job(job(),root,{},store_root=state)
    with path.open('a') as f:f.write(__import__('json').dumps({'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'新增一个要求，之前条件仍保留。'}]}})+'\n')
    second=process_coverage_job(job(),root,{},store_root=state)
    assert second['incremental']['reused_partition_drafts']>=3
    assert second['incremental']['semantic_acceptance_reused'] is False and second['model_calls']==0
    assert second['snapshot_id']!=first['snapshot_id']
    third=process_coverage_job(job(),root,{},store_root=state)
    assert third['partition_draft_cache_reused'] is True and third['snapshot_id']==second['snapshot_id']
