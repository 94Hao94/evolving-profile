import copy
import hashlib
import io
import json
import pytest
from lib.memory_recovery_scenario import request_source_coverage_review, CoverageError
from test_memory_recovery_scenario import fixture, response_with_intents


def encoded(result):
    return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}).encode()


@pytest.mark.parametrize('reason',['user_intent_supersession_invalid','user_intent_field_attribution_invalid'])
def test_one_mapping_reselection_uses_safe_location_and_binds_actual_second_request(tmp_path,reason):
    _,_,source,bundle,_=fixture(tmp_path)
    valid=response_with_intents(source,bundle);bad=copy.deepcopy(valid)
    intent=bad['user_intent_coverage'][0]['intents'][0]
    if reason=='user_intent_supersession_invalid':
        intent.update(disposition='superseded',superseded_by_ref='m3',superseding_quote=source['messages'][2]['text'])
    else:
        intent['field_links'][0].update(episode_ref='e2')
    calls=[]
    def opener(request,**_):
        calls.append(request.data)
        if len(calls)==2:
            body=json.loads(request.data);feedback=json.loads(body['messages'][-1]['content'].split('\n',1)[1])
            assert feedback['validation_error']['reason']==reason
            assert feedback['validation_error']['location']['message_ref']=='m1'
            assert feedback['validation_error']['location']['intent_index']==0
            assert body['messages'][1]['role']=='assistant'
            assert json.loads(body['messages'][1]['content'])==bad
            assert len(json.dumps(body['messages'],ensure_ascii=False))<=120000
        return io.BytesIO(encoded(bad if len(calls)==1 else valid))
    review=request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    receipt=review['model_review_receipt']
    assert len(calls)==2
    assert receipt['request_sha256']==hashlib.sha256(calls[1]).hexdigest()
    assert receipt['response_sha256']==hashlib.sha256(encoded(valid)).hexdigest()
    assert receipt['validation_feedback_history'][0]['request_sha256']==hashlib.sha256(calls[0]).hexdigest()
    assert receipt['validation_feedback_history'][0]['response_sha256']==hashlib.sha256(encoded(bad)).hexdigest()
    assert receipt['validation_feedback_history'][0]['validation_error']['reason']==reason


def test_reselection_never_retries_a_semantic_rejection_or_wrong_source(tmp_path):
    _,_,source,bundle,_=fixture(tmp_path)
    for mode in ['semantic','revision','role']:
        result=response_with_intents(source,bundle)
        if mode=='semantic':result.update(accept=False,issues=[{'code':'missing_scope'}])
        if mode=='revision':result['source_revision']='wrong-source'
        if mode=='role':result['reviewed_message_refs']=['m2','m1','m3','m4']
        calls=[]
        def opener(request,**_):calls.append(1);return io.BytesIO(encoded(result))
        with pytest.raises(CoverageError):
            request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
        assert len(calls)==1


def test_mapping_reselection_stops_after_one_failed_reselection(tmp_path):
    _,_,source,bundle,_=fixture(tmp_path);bad=response_with_intents(source,bundle)
    bad['user_intent_coverage'][0]['intents'][0]['field_links'][0]['episode_ref']='e2';calls=[]
    def opener(request,**_):calls.append(1);return io.BytesIO(encoded(bad))
    with pytest.raises(CoverageError) as caught:
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    assert caught.value.reason=='user_intent_field_attribution_invalid'
    assert len(calls)==2


def test_second_semantic_refusal_remains_a_refusal_without_third_request(tmp_path):
    _,_,source,bundle,_=fixture(tmp_path);bad=response_with_intents(source,bundle)
    bad['user_intent_coverage'][0]['intents'][0]['field_links'][0]['episode_ref']='e2'
    refusal=response_with_intents(source,bundle);refusal.update(accept=False,issues=[{'code':'no_valid_primary_field'}]);calls=[]
    def opener(request,**_):calls.append(1);return io.BytesIO(encoded(bad if len(calls)==1 else refusal))
    with pytest.raises(CoverageError) as caught:
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    assert caught.value.reason=='semantic_coverage_rejected' and len(calls)==2


def test_source_change_cannot_reuse_the_first_mapping_feedback(tmp_path):
    _,_,source,bundle,_=fixture(tmp_path);bad=response_with_intents(source,bundle)
    bad['user_intent_coverage'][0]['intents'][0]['field_links'][0]['episode_ref']='e2';calls=[]
    def opener(request,**_):
        calls.append(1);source['messages'][0]['text']+=' New source condition.'
        return io.BytesIO(encoded(bad))
    with pytest.raises(CoverageError) as caught:
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    assert caught.value.reason=='source_binding_mismatch' and len(calls)==1


def test_feedback_serialized_budget_is_checked_before_second_request(tmp_path,monkeypatch):
    from lib.scenario_review_catalog import review_catalog
    from lib.memory_recovery_scenario import source_coverage_review_prompt
    _,_,source,bundle,_=fixture(tmp_path);bad=response_with_intents(source,bundle)
    bad['user_intent_coverage'][0]['intents'][0]['field_links'][0]['episode_ref']='e2';calls=[]
    prompt=source_coverage_review_prompt(source,bundle,review_catalog(source,bundle))
    first_chars=len(json.dumps([{'role':'user','content':prompt}],ensure_ascii=False))
    monkeypatch.setattr('lib.memory_recovery_scenario.MAX_COVERAGE_INPUT_CHARS',first_chars+10)
    def opener(request,**_):calls.append(1);return io.BytesIO(encoded(bad))
    with pytest.raises(CoverageError) as caught:
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    assert caught.value.reason=='serialized_input_budget_exceeded' and len(calls)==1


def test_protected_source_never_reaches_initial_or_reselection_provider(tmp_path):
    _,_,source,bundle,_=fixture(tmp_path,prefix='不要写入记忆。')
    def forbidden(*args,**kwargs):raise AssertionError('Protected source reached provider')
    with pytest.raises(CoverageError) as caught:
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=forbidden)
    assert caught.value.reason=='source_permission_or_eligibility_rejected'


def test_feedback_location_cannot_carry_private_text_or_uncontrolled_paths():
    detail=CoverageError('user_intent_field_attribution_invalid',location={
        'message_ref':'m2','intent_index':3,'link_index':{'secret':'private'},
        'source_quote':'private source','state_path':'__class__/private'}).safe_detail()
    assert detail['location']=={'message_ref':'m2','intent_index':3}
    assert 'private' not in json.dumps(detail)


def test_bound_initial_feedback_can_make_exactly_one_new_review_request(tmp_path):
    from lib import memory_recovery_scenario as recovery
    _,_,source,bundle,_=fixture(tmp_path)
    builder=getattr(recovery,'source_coverage_validation_feedback',None)
    assert builder is not None,'Missing source-bound offline validation-feedback builder'
    feedback=builder(source,bundle,{'reason':'user_intent_supersession_invalid','fields':[],
                                   'location':{'message_ref':'m1','intent_index':0}})
    calls=[]
    def opener(request,**_):
        body=json.loads(request.data);calls.append(request.data)
        assert json.loads(body['messages'][-1]['content'].split('\n',1)[1])==feedback
        return io.BytesIO(encoded(response_with_intents(source,bundle)))
    review=recovery.request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',
        model='fixture',opener=opener,initial_validation_feedback=feedback,max_validation_reselections=0)
    assert len(calls)==1
    assert review['model_review_receipt']['request_sha256']==hashlib.sha256(calls[0]).hexdigest()
    bad=copy.deepcopy(feedback);bad['source_revision']='stale'
    def forbidden(*args,**kwargs):raise AssertionError('Stale feedback reached provider')
    with pytest.raises(CoverageError):
        recovery.request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',
            model='fixture',opener=forbidden,initial_validation_feedback=bad,max_validation_reselections=0)
