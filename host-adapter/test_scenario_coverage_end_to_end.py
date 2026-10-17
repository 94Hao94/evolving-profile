import json
from lib.scenario_coverage_incremental import process_coverage_job
from lib.scenario_coverage_read import read_coverage_view
from test_scenario_source_codec import SID,source
from test_scenario_coverage_incremental import job


def controlled_provider(calls):
    def provider(payload):
        calls.append(payload)
        if payload['protocol']=='segment-local-review.v1':
            spans=payload['partition']['primary']
            result={'accept':True,'read_span_ids':[s['span_id'] for s in spans],
                'intent_mappings':[{'span_id':s['span_id'],'start':0,'end':len(s['text']),'kind':'constraint','disposition':'unresolved'} for s in spans if s['role']=='user'],
                'issues':[],'assistant_reports_are_unverified':True}
        else:
            part=payload['part'];result={'accept':True,'read_requirement_ids':part['requirement_ids'],
                'reviewed_edge_ids':part['edge_ids'],'requirement_states':[{'requirement_id':rid,'status':'unresolved'} for rid in part['requirement_ids']],
                'relations':[],'issues':[]}
        return {'result':result,'usage':{'total_tokens':500},'transport':'isolated_fixture_not_live_provider'}
    return provider


def test_explicit_two_request_pilot_cannot_claim_task_completion_or_external_truth(tmp_path):
    root,_,_=source(tmp_path);calls=[];state=tmp_path/'state'
    result=process_coverage_job(job(),root,{'mode':'assisted','model_trial':True},store_root=state,provider=controlled_provider(calls))
    assert result['model_calls']==2 and len(calls)==2 and result['published'] is True
    nav=json.loads((state/'navigation'/f'{SID}.json').read_text())
    assert nav['schema']=='scenario-segmented-navigation.v1' and nav['legacy_v3_acceptance'] is False
    assert nav['coverage']['overall_complete'] is False and nav['external_fact_verified'] is False
    assert nav['has_unread_requirements'] is True and nav['source_readback'] is False


def test_restart_reuses_completed_stage_without_new_call_or_budget_reset(tmp_path):
    root,_,_=source(tmp_path);calls=[];state=tmp_path/'state';settings={'mode':'assisted','model_trial':True}
    first=process_coverage_job(job(),root,settings,store_root=state,provider=controlled_provider(calls))
    second=process_coverage_job(job(),root,settings,store_root=state,provider=controlled_provider(calls))
    assert first['published'] and second['published'] and second['model_calls']==0
    assert len(calls)==2 and second['budget']['requests_used']==2


def test_multiple_partitions_pause_without_globalizing_local_acceptance(tmp_path):
    root,_,_=source(tmp_path,text='不要删除，也不要发布。'*1000);calls=[];state=tmp_path/'state'
    result=process_coverage_job(job(),root,{'mode':'assisted','model_trial':True},store_root=state,provider=controlled_provider(calls))
    assert result['status']=='budget_paused' and result['model_calls']<=2
    assert result['published'] is False and not (state/'navigation'/f'{SID}.json').exists()
    page=read_coverage_view(state,SID,'requirements',permission=job()['permission'])
    assert page['requirements'][0]['intent_count']>0
    assert page['requirements'][0]['status']=='unresolved'


def test_reviewed_requirement_state_and_exact_intents_are_visible_in_navigation(tmp_path):
    root,_,_=source(tmp_path,text='不要发布；只检查。');state=tmp_path/'state';calls=[]
    base=controlled_provider(calls)
    def provider(payload):
        response=base(payload)
        if payload['protocol']=='segment-local-review.v1':
            for row in response['result']['intent_mappings']:row['disposition']='covered'
        if payload['protocol']=='segment-global-review.v1':
            for row in response['result']['requirement_states']:row['status']='covered'
        return response
    outcome=process_coverage_job(job(),root,{'mode':'assisted','model_trial':True},store_root=state,provider=provider)
    assert outcome['published'] is True
    nav=json.loads((state/'navigation'/f'{SID}.json').read_text())
    assert nav['current_conditions'][0]['source_quote']=='不要发布；只检查。'
    assert nav['intent_ledger'][0]['source_quote']=='不要发布；只检查。'
    assert nav['intent_ledger'][0]['source_locator']['scenario_id'].endswith('/turn/t1')
    page=read_coverage_view(state,SID,'requirements',permission=job()['permission'])
    assert page['requirements'][0]['status']=='covered'
    assert page['requirements'][0]['intent_count']==1


def test_whole_message_covered_does_not_promote_a_superseded_local_clause(tmp_path):
    root,_,_=source(tmp_path,text='旧值100；改为200。');state=tmp_path/'state';calls=[];base=controlled_provider(calls)
    def provider(payload):
        response=base(payload)
        if payload['protocol']=='segment-local-review.v1':
            span=next(s for s in payload['partition']['primary'] if s['role']=='user')
            response['result']['intent_mappings']=[{'span_id':span['span_id'],'start':0,'end':6,'kind':'constraint','disposition':'superseded'},
                {'span_id':span['span_id'],'start':6,'end':len(span['text']),'kind':'correction','disposition':'covered'}]
        else:
            for row in response['result']['requirement_states']:row['status']='covered'
        return response
    outcome=process_coverage_job(job(),root,{'mode':'assisted','model_trial':True},store_root=state,provider=provider)
    assert outcome['published']
    nav=json.loads((state/'navigation'/f'{SID}.json').read_text())
    assert all('100' not in row['source_quote'] for row in nav['current_conditions'])
    assert nav['historical_conditions'][0]['source_quote']=='旧值100；'


def test_local_omission_cannot_disappear_in_global_covered_state(tmp_path):
    root,_,_=source(tmp_path);calls=[];base=controlled_provider(calls)
    def provider(payload):
        response=base(payload)
        if payload['protocol']=='segment-local-review.v1':
            for m in response['result']['intent_mappings']:m['disposition']='omitted'
        else:
            for m in response['result']['requirement_states']:m['status']='covered'
        return response
    result=process_coverage_job(job(),root,{'mode':'assisted','model_trial':True},store_root=tmp_path/'state',provider=provider)
    assert result['published'] is False


def test_selection_contract_upgrade_pauses_without_refreshing_original_allowance(tmp_path,monkeypatch):
    from lib import scenario_coverage_store
    root,_,_=source(tmp_path);calls=[];state=tmp_path/'state';settings={'mode':'assisted','model_trial':True}
    process_coverage_job(job(),root,settings,store_root=state,provider=controlled_provider(calls))
    original=scenario_coverage_store.contract
    monkeypatch.setattr(scenario_coverage_store,'contract',lambda:{**original(),'source_selection_version':'future-test-contract'})
    later=process_coverage_job(job(),root,settings,store_root=state,provider=controlled_provider(calls))
    assert later['status']=='budget_paused' and later['model_calls']==0 and len(calls)==2
