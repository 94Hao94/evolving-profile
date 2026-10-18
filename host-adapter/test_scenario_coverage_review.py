import pytest
from lib.scenario_coverage_budget import CoverageBudget
from lib.scenario_coverage_partition import partition_snapshot
from lib.scenario_coverage_review import review_partition,local_payload
from lib.scenario_coverage_contract import fingerprint,canonical
from test_scenario_coverage_partition import snapshot


def fixture(tmp_path):
    snap=snapshot(tmp_path,'不要发布；只检查。');part=partition_snapshot(snap,capacity=1000)['partitions'][0]
    ledger=CoverageBudget(tmp_path/'b.sqlite',job_id='j',budget_identity=snap['semantic_budget_identity'],parent_attempts=1,max_requests=2,max_tokens=16000)
    return part,ledger


def accepted(part):
    return {'accept':True,'read_span_ids':[s['span_id'] for s in part['primary']],
        'intent_mappings':[{'span_id':s['span_id'],'start':0,'end':len(s['text']),'kind':'constraint','disposition':'unresolved'} for s in part['primary'] if s['role']=='user'],
        'issues':[],'assistant_reports_are_unverified':True}


def test_no_reservation_or_zero_budget_never_calls_provider(tmp_path):
    part,ledger=fixture(tmp_path);calls=[]
    with pytest.raises(ValueError,match='reservation_required'):review_partition(part,{},lambda p:calls.append(p),None,ledger)
    assert calls==[]


def test_local_acceptance_cannot_claim_global_or_external_facts(tmp_path):
    part,ledger=fixture(tmp_path);r=ledger.reserve_request('local',fingerprint(local_payload(part,{})),4000)
    result=review_partition(part,{},lambda payload:{'result':accepted(part),'usage':{'total_tokens':1500}},r,ledger)
    assert result['status']=='local_reviewed' and result['overall_complete'] is False
    assert result['external_fact_verified'] is False and result['response_sha256']
    assert ledger.status()['charged_tokens']==1500


def test_missing_condition_span_is_rejected_and_timeout_charged_unknown(tmp_path):
    part,ledger=fixture(tmp_path);bad=accepted(part);bad['intent_mappings'][0]['end']-=2
    r=ledger.reserve_request('local',fingerprint(local_payload(part,{})),4000)
    result=review_partition(part,{},lambda payload:{'result':bad,'usage':{'total_tokens':700}},r,ledger)
    assert result['status']=='rejected' and result['reason']=='intent_coverage_incomplete'
    r2=ledger.reserve_request('local',fingerprint(local_payload(part,{'retry':'new-input'})),len(canonical(local_payload(part,{'retry':'new-input'})))+2000)
    def timeout(payload):raise TimeoutError()
    result=review_partition(part,{'retry':'new-input'},timeout,r2,ledger)
    assert result['status']=='unavailable' and ledger.status()['unknown_usage_requests']==1


def test_reservation_for_different_input_never_dispatches(tmp_path):
    part,ledger=fixture(tmp_path);calls=[];r=ledger.reserve_request('other','different',4000)
    with pytest.raises(ValueError,match='reservation_input_mismatch'):
        review_partition(part,{},lambda payload:calls.append(payload),r,ledger)
    assert calls==[] and ledger.status()['reserved_requests']==1


def test_empty_normalized_metadata_is_read_but_not_required_to_be_a_user_intent(tmp_path):
    from lib.scenario_coverage_review import validate_local_result
    part,_=fixture(tmp_path)
    part['primary'].append({**part['primary'][0],'span_id':'empty-metadata','text':''})
    result=accepted(part)
    result['intent_mappings']=[m for m in result['intent_mappings'] if m['span_id']!='empty-metadata']
    assert validate_local_result(part,result) is None


def test_payload_declares_user_only_mapping_schema_and_exact_unicode_bounds(tmp_path):
    part,_=fixture(tmp_path)
    payload=local_payload(part,{})
    assert payload['output_contract']['intent_mappings']['roles']==['user']
    assert payload['output_contract']['assistant_reports_are_unverified']=='top_level_boolean_true'
    assert 'constraint' in payload['output_contract']['intent_mappings']['kind_enum']
    assert 'unresolved' in payload['output_contract']['intent_mappings']['disposition_enum']
    first=part['primary'][0]
    assert payload['span_catalog'][0]['text_length']==len(first['text'])
