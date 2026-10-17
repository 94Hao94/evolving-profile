"""Malformed reference copying can be reselected once, never silently repaired."""
import copy,hashlib,io,json
import pytest
from lib.memory_recovery_scenario import request_source_coverage_review,CoverageError
from test_memory_recovery_scenario import fixture,response_with_intents

ERRORS=['user_intent_source_quote_invalid','user_intent_field_quote_invalid','user_intent_summary_mapping_invalid']

def bad_mapping(valid,reason):
    value=copy.deepcopy(valid);intent=value['user_intent_coverage'][0]['intents'][0]
    if reason=='user_intent_source_quote_invalid':intent['source_quote']='This was not the user request.'
    elif reason=='user_intent_field_quote_invalid':intent['field_links'][0]['field_quote']='Not the state field.'
    else:intent['field_links'][0]['summary_paths']=['compact']
    return value

def response(value):
    return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}).encode()

@pytest.mark.parametrize('reason',ERRORS)
def test_copy_mapping_error_is_located_and_reselected_once_without_changing_verdict(tmp_path,reason):
    _,_,source,bundle,_=fixture(tmp_path);valid=response_with_intents(source,bundle)
    malformed=bad_mapping(valid,reason);calls=[]
    def opener(request,**_):
        calls.append(request.data)
        if len(calls)==2:
            body=json.loads(request.data)
            feedback=json.loads(body['messages'][-1]['content'].split('\n',1)[1])
            assert feedback['validation_error']['reason']==reason
            assert feedback['validation_error']['location']['message_ref']=='m1'
            assert feedback['validation_error']['location']['intent_index']==0
            if reason!='user_intent_source_quote_invalid':assert feedback['validation_error']['location']['link_index']==0
            assert json.loads(body['messages'][1]['content'])==malformed
        return io.BytesIO(response(malformed if len(calls)==1 else valid))
    audit=request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    assert len(calls)==2
    assert audit['user_intent_coverage'][0]['intents'][0]['source_quote']=='请编制项目甲方案'
    assert audit['accept'] is True
    receipt=audit['model_review_receipt']
    assert receipt['request_sha256']==hashlib.sha256(calls[1]).hexdigest()
    assert receipt['response_sha256']==hashlib.sha256(response(valid)).hexdigest()
    assert receipt['validation_feedback_history'][0]['response_sha256']==hashlib.sha256(response(malformed)).hexdigest()

@pytest.mark.parametrize('reason',ERRORS)
def test_copy_mapping_reselection_never_adds_a_third_call(tmp_path,reason):
    _,_,source,bundle,_=fixture(tmp_path);bad=bad_mapping(response_with_intents(source,bundle),reason);calls=[]
    def opener(request,**_):calls.append(request.data);return io.BytesIO(response(bad))
    with pytest.raises(CoverageError) as caught:
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    assert caught.value.reason==reason and len(calls)==2

@pytest.mark.parametrize('reason',ERRORS)
def test_copy_mapping_repair_honors_disabled_reselection_and_semantic_refusal(tmp_path,reason):
    _,_,source,bundle,_=fixture(tmp_path);valid=response_with_intents(source,bundle);bad=bad_mapping(valid,reason)
    for enabled in [False,True]:
        calls=[];refusal={**valid,'accept':False,'issues':[{'code':'source_condition_missing'}]}
        def opener(request,**_):calls.append(request.data);return io.BytesIO(response(bad if len(calls)==1 else refusal))
        with pytest.raises(CoverageError) as caught:
            request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener,max_validation_reselections=int(enabled))
        assert len(calls)==(2 if enabled else 1)
        assert caught.value.reason==('semantic_coverage_rejected' if enabled else reason)
