"""Model selection of exact clauses avoids rewriting away conditions."""
import io,json
import pytest
from lib.scenario_model import _request_session_state_single
from test_scenario_state_v3 import source,claim


def fixture(reference):
    original=source([('user','如果容量不足，才使用后备；不要发布原始资料。'),('assistant','已答复，但结果未核验')])
    state={'subject':claim('资料处理','id1'),'goal':claim('保持原始条件','id1'),'phase':'assistant_reported',
           'constraints':[reference],'corrections':[],
           'assistant_reports':[claim('已答复，但结果未核验','id2')],'unresolved':[]}
    return original,state


def call(original,state):
    requests=[]
    def reply(request,**kwargs):
        requests.append(json.loads(request.data))
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'source_revision':original['source_revision'],'state':state})}}]}).encode())
    result=_request_session_state_single(original,base_url='https://invalid.test',api_key='test',model='test',opener=reply)
    return result,requests


def test_provider_can_select_an_exact_clause_without_copying_or_losing_the_condition():
    original,state=fixture({'clause_index':1,'message_ids':['id1']})
    draft,requests=call(original,state)
    assert draft['state']['constraints']==[{'text':'如果容量不足，才使用后备；','message_ids':['id1']}]
    assert '如果容量不足，才使用后备；' in draft['summaries']['full']
    assert len(requests)==1
    payload=json.loads(requests[0]['messages'][-1]['content'].split('输入：',1)[1])
    assert payload['user_clause_catalog'][0]['clauses'][1]['clause_index']==1


@pytest.mark.parametrize('reference',[
    {'clause_index':999,'message_ids':['id1']},
    {'clause_index':-1,'message_ids':['id1']},
    {'clause_index':True,'message_ids':['id1']},
    {'clause_index':1,'message_ids':['id2']},
    {'clause_index':1,'message_ids':['id1','id2']},
    {'clause_index':1,'message_ids':['unknown']},
    {'clause_index':1,'message_ids':['id1'],'text':'可以发布'},
    {'clause_index':1,'message_ids':['id1'],'source_span':[0,1]},
])
def test_invalid_or_ambiguous_references_never_become_claims(reference):
    original,state=fixture(reference)
    with pytest.raises(ValueError):call(original,state)


def test_clause_selection_does_not_bypass_role_and_field_boundaries():
    original,state=fixture(claim('不要发布原始资料。','id1'))
    state['assistant_reports']=[{'clause_index':1,'message_ids':['id1']}]
    with pytest.raises(ValueError):call(original,state)


def test_explicit_text_cannot_bypass_the_same_ineligible_catalog_entry():
    original,state=fixture(claim('password=12345678','id1'))
    original['messages'][0]['text']='password=12345678'
    from lib.scenario_state_v3 import user_clause_catalog
    assert user_clause_catalog(original)[0]['clauses'][0]['eligible'] is False
    with pytest.raises(ValueError):call(original,state)
