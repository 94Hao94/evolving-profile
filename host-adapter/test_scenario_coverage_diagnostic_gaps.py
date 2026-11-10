"""Precise failure locations and one shared full-response correction allowance."""
import copy
import hashlib
import io
import json

import pytest

from lib.memory_recovery_scenario import (CoverageError, request_source_coverage_review,
                                         validate_user_intent_coverage)
from test_memory_recovery_scenario import fixture, response_with_intents


def encoded(value, finish='stop', *, raw=False):
    return json.dumps({'choices':[{'finish_reason':finish,'message':{
        'content':value if raw else json.dumps(value)}}]}).encode()


def malformed(valid, kind):
    value=copy.deepcopy(valid);entry=value['user_intent_coverage'][0];intent=entry['intents'][0]
    if kind=='non_substantive':intent.update(kind='acknowledgment',disposition='non_substantive',field_links=[])
    elif kind=='answer':intent.update(disposition='answered',answer_message_ref='m1')
    elif kind=='path':intent['field_links'][0]['state_path']='constraints/99/text'
    elif kind=='episode':intent['field_links'][0]['episode_ref']='e99'
    elif kind=='entry':entry['intents']=[]
    elif kind=='manifest':value['user_intent_coverage'].pop(0)
    elif kind=='omitted':intent.update(disposition='omitted',omission_reason='No matching claim.')
    elif kind=='link_shape':intent['field_links'][0]='invalid'
    elif kind=='intent_shape':entry['intents'][0]='invalid'
    return value


REASONS={'non_substantive':'user_intent_non_substantive_invalid','answer':'user_intent_answer_invalid',
         'path':'user_intent_field_path_invalid','episode':'user_intent_field_path_invalid',
         'entry':'user_intent_coverage_missing','manifest':'user_intent_coverage_missing',
         'omitted':'user_intent_omitted','link_shape':'user_intent_mapping_invalid',
         'intent_shape':'user_intent_mapping_invalid'}

@pytest.mark.parametrize('mode',['earlier_bad_path','omitted_bad_quote','omitted_bad_catalog_ref'])
def test_explicit_omission_wins_over_any_earlier_retryable_error(tmp_path,mode):
    _,_,source,bundle,_=fixture(tmp_path);valid=response_with_intents(source,bundle);bad=copy.deepcopy(valid)
    if mode=='earlier_bad_path':
        assert len(bad['user_intent_coverage'])>1
        bad['user_intent_coverage'][0]['intents'][0]['field_links'][0]['state_path']='constraints/99/text'
        entry=bad['user_intent_coverage'][-1]
    else:entry=bad['user_intent_coverage'][0]
    intent=entry['intents'][0];intent.update(disposition='omitted',omission_reason='Specific source intent missing')
    if mode=='omitted_bad_quote':intent['source_quote']='not present in source'
    if mode=='omitted_bad_catalog_ref':intent['source_quote_ref']='missing-catalog-choice'
    calls=[]
    def opener(request,**kwargs):
        calls.append(request.data);return io.BytesIO(encoded(bad if len(calls)==1 else valid))
    with pytest.raises(CoverageError) as caught:
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='test',opener=opener)
    assert caught.value.reason=='user_intent_omitted'
    assert caught.value.safe_detail()['location']['message_ref']==entry['message_ref']
    assert len(calls)==1


@pytest.mark.parametrize('kind',list(REASONS))
def test_known_mapping_scope_has_exact_safe_location(tmp_path,kind):
    _,_,source,bundle,_=fixture(tmp_path);bad=malformed(response_with_intents(source,bundle),kind)
    with pytest.raises(CoverageError) as caught:
        validate_user_intent_coverage(source,bundle,bad['user_intent_coverage'])
    assert caught.value.reason==REASONS[kind]
    expected={'message_ref':'m1'}
    if kind not in {'entry','manifest'}:expected['intent_index']=0
    if kind in {'path','episode','link_shape'}:expected['link_index']=0
    assert caught.value.safe_detail()['location']==expected


@pytest.mark.parametrize('kind',[k for k in REASONS if k!='omitted'])
def test_mapping_shape_gets_one_fresh_response_with_existing_budget(tmp_path,kind):
    _,_,source,bundle,_=fixture(tmp_path);valid=response_with_intents(source,bundle);bad=malformed(valid,kind);calls=[]
    def opener(request,**kwargs):
        calls.append(request.data)
        return io.BytesIO(encoded(bad if len(calls)==1 else valid))
    audit=request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='test',opener=opener)
    assert len(calls)==2
    assert audit['model_review_receipt']['response_sha256']==hashlib.sha256(encoded(valid)).hexdigest()
    feedback=json.loads(json.loads(calls[1])['messages'][-1]['content'].split('\n',1)[1])
    assert feedback['validation_error']['reason']==REASONS[kind]
    assert feedback['validation_error']['location']['message_ref']=='m1'


@pytest.mark.parametrize('first',['{invalid JSON','[]','```json\n{broken\n```'])
def test_completed_invalid_json_gets_one_full_regeneration_not_salvage(tmp_path,first):
    _,_,source,bundle,_=fixture(tmp_path);valid=response_with_intents(source,bundle);calls=[]
    def opener(request,**kwargs):
        calls.append(request.data)
        return io.BytesIO(encoded(first,raw=True) if len(calls)==1 else encoded(valid))
    audit=request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='test',opener=opener)
    assert len(calls)==2
    history=audit['model_review_receipt']['validation_feedback_history']
    assert history[0]['validation_error']=={'reason':'model_response_invalid','fields':[]}
    assert history[0]['response_sha256']==hashlib.sha256(encoded(first,raw=True)).hexdigest()
    assert audit['model_review_receipt']['response_sha256']==hashlib.sha256(encoded(valid)).hexdigest()


@pytest.mark.parametrize('sequence',['parse_mapping','mapping_parse','parse_parse'])
def test_parse_and_mapping_errors_share_one_total_correction_budget(tmp_path,sequence):
    _,_,source,bundle,_=fixture(tmp_path);valid=response_with_intents(source,bundle)
    parse=encoded('{broken',raw=True);mapping=encoded(malformed(valid,'path'));calls=[]
    responses={'parse_mapping':[parse,mapping],'mapping_parse':[mapping,parse],'parse_parse':[parse,parse]}[sequence]
    def opener(request,**kwargs):calls.append(request.data);return io.BytesIO(responses[len(calls)-1])
    with pytest.raises(CoverageError):
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='test',opener=opener)
    assert len(calls)==2


@pytest.mark.parametrize('mode',['disabled','truncated','noncompleted','outer_json_invalid','omitted','veto_and_mapping','veto_and_bad_selection'])
def test_no_correction_for_disabled_incomplete_or_semantically_rejected_response(tmp_path,mode):
    _,_,source,bundle,_=fixture(tmp_path);value=response_with_intents(source,bundle);calls=[]
    if mode=='omitted':value=malformed(value,'omitted')
    if mode=='veto_and_mapping':value=malformed(value,'path');value['accept']=False
    if mode=='veto_and_bad_selection':
        value['accept']=False;value['user_intent_coverage'][0]['intents'][0]['source_quote_ref']='nonexistent'
    response=encoded(value)
    if mode=='disabled':response=encoded('{broken',raw=True)
    if mode=='truncated':response=encoded('{broken',finish='length',raw=True)
    if mode=='noncompleted':response=encoded('{broken',finish='content_filter',raw=True)
    if mode=='outer_json_invalid':response=b'{broken transport'
    def opener(request,**kwargs):calls.append(request.data);return io.BytesIO(response)
    with pytest.raises(CoverageError):
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='test',opener=opener,
                                       max_validation_reselections=0 if mode=='disabled' else 1)
    assert len(calls)==1


@pytest.mark.parametrize('kind',['reordered','non_list','extra_only'])
def test_manifest_error_does_not_invent_focus_when_no_user_is_provably_absent(tmp_path,kind):
    _,_,source,bundle,_=fixture(tmp_path);manifest=response_with_intents(source,bundle)['user_intent_coverage']
    if kind=='reordered':manifest.reverse()
    if kind=='non_list':manifest=None
    if kind=='extra_only':manifest.append({'message_ref':'m999','intents':[]})
    with pytest.raises(CoverageError) as caught:validate_user_intent_coverage(source,bundle,manifest)
    assert caught.value.reason=='user_intent_coverage_missing'
    assert 'location' not in caught.value.safe_detail()


@pytest.mark.parametrize('flag',['whole_source_topics_covered','corrections_preserved','assistant_claims_labeled','partition_exact','accept'])
def test_every_semantic_veto_wins_before_invalid_catalog_mapping(tmp_path,flag):
    _,_,source,bundle,_=fixture(tmp_path);value=malformed(response_with_intents(source,bundle),'path')
    value[flag]=False;value['user_intent_coverage'][0]['intents'][0]['source_quote_ref']='wrong-catalog-ref';calls=[]
    def opener(request,**kwargs):calls.append(1);return io.BytesIO(encoded(value))
    with pytest.raises(CoverageError) as caught:
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='test',opener=opener)
    assert caught.value.reason=='semantic_coverage_rejected'
    assert flag in caught.value.fields
    assert len(calls)==1


def test_parse_correction_remains_subject_to_provider_budget_exception(tmp_path):
    _,_,source,bundle,_=fixture(tmp_path);calls=[]
    def opener(request,**kwargs):
        calls.append(1)
        if len(calls)==2:raise ValueError('provider_budget_exhausted')
        return io.BytesIO(encoded('{broken',raw=True))
    with pytest.raises(ValueError,match='provider_budget_exhausted'):
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='test',opener=opener)
    assert len(calls)==2


def test_parse_failure_never_overrides_changed_source_binding(tmp_path):
    _,_,source,bundle,_=fixture(tmp_path);calls=[]
    def opener(request,**kwargs):
        calls.append(1);source['messages'][0]['text']+=' changed'
        return io.BytesIO(encoded('{broken',raw=True))
    with pytest.raises(CoverageError) as caught:
        request_source_coverage_review(source,bundle,base_url='https://fixture.invalid',api_key='test',model='test',opener=opener)
    assert caught.value.reason=='source_binding_mismatch'
    assert len(calls)==1
