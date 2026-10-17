import json
import sys
from pathlib import Path
import pytest

from test_scenario_source_codec import SID,source
from test_scenario_coverage_incremental import job
from test_scenario_coverage_end_to_end import controlled_provider
from lib.scenario_coverage_incremental import process_coverage_job
from lib.scenario_coverage_read import read_coverage_view
from lib.scenario_coverage_contract import canonical,fingerprint
from lib.scenario_source_codec import decode_record

def append_user(path,text):
    with path.open('a') as f:
        f.write(json.dumps({'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':text}]}})+'\n')

def test_native_phase_final_answer_is_selected():
    raw=json.dumps({'type':'response_item','payload':{'type':'message','role':'assistant','phase':'final_answer','content':[{'type':'output_text','text':'The requested work is not finished.'}]}}).encode()
    unit,_=decode_record(raw,2,0,'t1',SID)
    assert unit['selection']=='visible_message' and unit['role']=='assistant'

def test_configured_partition_limits_are_effective(tmp_path):
    root,_,_=source(tmp_path,text='abc '*1000)
    state=tmp_path/'state'
    process_coverage_job(job(),root,{'limits':{'partition_input_tokens':100,'context_tokens':1}},store_root=state)
    inv=json.loads((state/'inventories'/f'{SID}.json').read_text())
    assert inv['partition_plan']['capacity']==100
    assert inv['partition_plan']['context_tokens']==1

def test_append_returns_outcome_with_original_budget(tmp_path):
    root,path,_=source(tmp_path);state=tmp_path/'state';settings={'mode':'assisted','model_trial':True};calls=[]
    process_coverage_job(job(),root,settings,store_root=state,provider=controlled_provider(calls))
    append_user(path,'New independent requirement.')
    result=process_coverage_job(job(),root,settings,store_root=state,provider=controlled_provider(calls))
    assert result['status'] in {'budget_paused','partial','global_pending'}

def test_changed_provider_does_not_reuse_semantic_accept(tmp_path):
    root,_,_=source(tmp_path);state=tmp_path/'state';settings={'mode':'assisted','model_trial':True};calls=[]
    class Provider:
        def __init__(self,model):self.config={'EVOLVING_PROFILE_API_LLM_MODEL':model};self.inner=controlled_provider(calls)
        def __call__(self,payload):return {**self.inner(payload),'model':self.config['EVOLVING_PROFILE_API_LLM_MODEL']}
    process_coverage_job(job(),root,settings,store_root=state,provider=Provider('model-A'))
    result=process_coverage_job(job(),root,settings,store_root=state,provider=Provider('model-B'))
    assert not result['published'], 'Changed model silently restored old accept with zero requests'
    page=read_coverage_view(state,SID,'requirements',permission=job()['permission'])
    assert page['requirements'][0]['intent_count']==0, 'Old-model intent acceptance was presented as current'

def test_requirement_page_bounds_all_nested_text(tmp_path):
    root,path,raw=source(tmp_path,text='Please inspect this.')
    rows=[json.loads(s) for s in raw.splitlines()]
    rows[-1]['payload']['content'][0]['text']='x'*300000
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    state=tmp_path/'state';process_coverage_job(job(),root,{},store_root=state)
    result=read_coverage_view(state,SID,'requirements',permission=job()['permission'])
    assert len(canonical(result))<=256*1024, len(canonical(result))

def test_actual_reported_conflicts_prevent_accept(tmp_path):
    from lib.scenario_coverage_store import CoverageStore
    from lib.scenario_coverage_partition import partition_snapshot,build_requirement_catalog
    from lib.scenario_coverage_review import review_partition,local_payload
    from lib.scenario_coverage_budget import CoverageBudget
    from lib.scenario_global_review import plan_global_review,global_payload,review_global_partition,validate_global_coverage
    root,path,_=source(tmp_path,text='Budget is 100.')
    append_user(path,'Budget is 200.')
    state=tmp_path/'state';out=process_coverage_job(job(),root,{},store_root=state)
    snap=CoverageStore(state/'coverage.sqlite3').read(out['snapshot_id'])
    plan=partition_snapshot(snap,capacity=20)
    reqs=build_requirement_catalog(plan)
    budget=CoverageBudget(state/'probe.sqlite3',job_id='probe',budget_identity='test',parent_attempts=0,max_requests=100,max_tokens=1000000)
    local=[]
    for p in plan['partitions']:
        payload=local_payload(p,{})
        r=budget.reserve_request('local',fingerprint(payload),len(canonical(payload))+2000)
        local.append(review_partition(p,{},controlled_provider([]),r,budget))
    ledger={'partition_plan':plan,'requirements':reqs,'local_reviews':local}
    gp=plan_global_review(snap,ledger);byid={r['requirement_id']:r for r in reqs['requirements']};receipts=[]
    def provider(payload):
        p=payload['part'];ids=p['requirement_ids']
        rel=[{'type':'conflicts','from':ids[0],'to':ids[1]}] if p['kind']=='boundary' else []
        return {'result':{'accept':True,'issues':[],'read_requirement_ids':ids,'reviewed_edge_ids':p['edge_ids'],'requirement_states':[{'requirement_id':rid,'status':'covered'} for rid in ids],'relations':rel},'usage':{'total_tokens':10}}
    for p in gp['parts']:
        payload=global_payload(p,byid.__getitem__,plan=gp)
        r=budget.reserve_request('global',fingerprint(payload),len(canonical(payload))+2000)
        receipts.append(review_global_partition(p,byid.__getitem__,provider,r,budget,plan=gp))
    coverage=validate_global_coverage(gp,receipts,ledger)
    assert coverage['relations'], 'Fixture must contain an explicit conflict'
    assert coverage['status']=='conflicted' and not coverage['overall_complete'], coverage

def test_changed_scope_cannot_restore_old_accept(tmp_path):
    root,_,_=source(tmp_path);state=tmp_path/'state';settings={'mode':'assisted','model_trial':True};calls=[]
    first=process_coverage_job(job(),root,settings,store_root=state,provider=controlled_provider(calls))
    changed={**job(),'bank_id':'different-bank','project_key':'different-project'}
    second=process_coverage_job(changed,root,settings,store_root=state,provider=controlled_provider(calls))
    assert not second['published'] or second['snapshot_id']!=first['snapshot_id']

def test_interrupted_dispatch_is_unknown_on_restart(tmp_path):
    root,_,_=source(tmp_path);state=tmp_path/'state';settings={'mode':'assisted','model_trial':True}
    def interrupted(payload):raise SystemExit('simulate process death after dispatch')
    with pytest.raises(SystemExit):
        process_coverage_job(job(),root,settings,store_root=state,provider=interrupted)
    result=process_coverage_job(job(),root,settings,store_root=state,provider=controlled_provider([]))
    assert result['budget']['unknown_usage_requests']==1, result

def test_relations_pagination_reaches_all_rows(tmp_path):
    root,_,_=source(tmp_path);state=tmp_path/'state'
    outcome=process_coverage_job(job(),root,{},store_root=state)
    directory=state/'navigation';directory.mkdir()
    (directory/f'{SID}.json').write_text(json.dumps({'snapshot_id':outcome['snapshot_id'],'coverage':{'relations':[{'test_relation':i} for i in range(21)]}}))
    result=read_coverage_view(state,SID,'relations',permission=job()['permission'])
    assert len(result['relations'])==20
    assert result['coverage_cursor'], 'The 21st relation has no continuation cursor'

def test_same_partition_correction_can_be_reviewed_together(tmp_path):
    from lib.scenario_coverage_store import CoverageStore
    from lib.scenario_coverage_partition import partition_snapshot,build_requirement_catalog
    from lib.scenario_global_review import plan_global_review
    root,path,_=source(tmp_path,text='Budget is 100.')
    append_user(path,'Correction: replace 100 with 200.')
    state=tmp_path/'state';out=process_coverage_job(job(),root,{},store_root=state)
    snap=CoverageStore(state/'coverage.sqlite3').read(out['snapshot_id']);plan=partition_snapshot(snap)
    assert len(plan['partitions'])==1
    ledger={'partition_plan':plan,'requirements':build_requirement_catalog(plan),'local_reviews':[]}
    gp=plan_global_review(snap,ledger)
    assert any(len(p['requirement_ids'])==2 for p in gp['parts']), 'No request can produce a validated supersedes relation between these two requirements'


def test_prepared_compressed_turn_has_raw_readback_route(tmp_path):
    from lib.raw_session_evidence import read_evidence
    root,_,_=source(tmp_path,compressed=True)
    result=process_coverage_job(job(),root,{},store_root=tmp_path/'state')
    assert result['source_manifest_complete']
    raw=read_evidence(SID,root,turn_id='t1',cache_root=tmp_path/'raw-cache')
    assert raw['status']=='source_read' and raw.get('source',{}).get('text'), raw
