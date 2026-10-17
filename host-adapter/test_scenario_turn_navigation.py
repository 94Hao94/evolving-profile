import io
import json

from lib.scenario_model import _request_session_state_single
from lib.scenario_review_catalog import review_catalog, review_transport
from test_scenario_state_v3 import source, claim
from test_memory_recovery_scenario import fixture


def test_draft_wire_keeps_earlier_turns_when_current_goal_moves():
    original=source([('user','解释编码'),('assistant','编码的答复'),
        ('assistant','补充限制'),('user','改为比较方法'),('assistant','方法比较')])
    def opener(request,**kwargs):
        messages=json.loads(request.data)['messages']
        assert messages[0]['role']=='system'
        assert '解释编码' not in messages[0]['content']
        payload=json.loads(next(m['content'] for m in messages if m['role']=='user').split('输入：',1)[1])
        assert payload['source_turn_inventory']==[
            {'user_message_id':'id1','following_assistant_candidate_ids':['id2','id3']},
            {'user_message_id':'id4','following_assistant_candidate_ids':['id5']}]
        assert [m['text'] for m in payload['messages']]==['解释编码','编码的答复','补充限制','改为比较方法','方法比较']
        state={'subject':claim('学习方法','id1'),'goal':claim('比较方法','id4'),
            'phase':'assistant_reported','constraints':[],'corrections':[claim('改为比较方法','id4')],
            'assistant_reports':[claim('编码的答复','id2'),claim('方法比较','id5')],'unresolved':[]}
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(
            {'source_revision':'revision-1','state':state})}}]}).encode())
    draft=_request_session_state_single(original,base_url='https://fixture.invalid',api_key='test',model='test',opener=opener)
    assert [r['message_ids'] for r in draft['state']['assistant_reports']]==[['id2'],['id5']]
    assert draft['state']['corrections'][0]['text']=='改为比较方法'


def test_inventory_does_not_infer_answeredness_or_attach_assistant_before_user():
    from lib.scenario_state_v3 import source_turn_inventory
    assert source_turn_inventory(source([]))==[]
    assert source_turn_inventory(source([('assistant','旧报告'),('user','问题甲'),('user','问题乙')]))==[
        {'user_message_id':'id2','following_assistant_candidate_ids':[]},
        {'user_message_id':'id3','following_assistant_candidate_ids':[]}]


def test_host_episode_bounds_do_not_follow_goal_anchor(tmp_path):
    _,_,original,bundle,_=fixture(tmp_path)
    ep=bundle['episodes'][0]
    wire=review_transport(original,bundle,review_catalog(original,bundle))
    assert wire['episodes'][0]['host_source_range']=={
        'first_message_ref':'m1','last_message_ref':'m2','message_count':2,
        'authority':'host_episode_membership_not_state_claim_anchors'}
    assert ep['message_ids']==[m['evidence_id'] for m in original['messages'][:2]]


def test_full_paragraph_selector_never_forces_join_across_blank_line():
    from lib.scenario_state_v3 import whole_user_clauses
    raw='Please compare methods without executing anything\n\n[quoted context]\nDo not erase this evidence.'
    clauses=whole_user_clauses(raw)
    assert 'Please compare methods without executing anything' in clauses
    assert '[quoted context] Do not erase this evidence.' in clauses
    # Neither paragraph is deleted or assigned semantic authority by parsing.
    assert ' '.join(raw.split()) in clauses


def test_long_quote_catalog_uses_exact_source_locations_instead_of_duplicate_text():
    raw='Only draft, do not publish. '+('x'*140)+'\n\nRetain the condition and uncertainty.'
    original=source([('user',raw),('assistant','Draft only, unverified')])
    def opener(request,**kwargs):
        data=json.loads(next(m['content'] for m in json.loads(request.data)['messages'] if m['role']=='user').split('输入：',1)[1])
        option=data['user_clause_catalog'][0]['clauses'][0]
        assert 'text' not in option and option['source_span']==[0,len(raw)]
        assert data['messages'][0]['text']==raw
        state={'subject':claim('Draft','id1'),'goal':claim('Retain conditions','id1'),'phase':'assistant_reported',
            'constraints':[{'clause_index':0,'message_ids':['id1']}],'corrections':[],
            'assistant_reports':[claim('Draft only, unverified','id2')],'unresolved':[]}
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(
            {'source_revision':'revision-1','state':state})}}]}).encode())
    draft=_request_session_state_single(original,base_url='https://fixture.invalid',api_key='test',model='test',opener=opener)
    assert draft['state']['constraints'][0]['text']=='Only draft, do not publish. '+('x'*140)+' Retain the condition and uncertainty.'
