import copy
import io
import json
import pytest
from lib.scenario_source import revision_for_messages
from lib.scenario_state_v3 import validate_state_draft, state_partition_source
from lib.scenario_episodes import validate_episode_bundle, partition_source
from lib.scenario_model import fingerprint_episode_bundle

def fixture(focus_text='Try again'):
    rows=[]
    for i,(role,text) in enumerate([('user','Create the document.'),('assistant','Request timed out.'),
        ('user',focus_text),('user','Try again'),('assistant','API 524 timeout.'),('user','Try again'),
        ('user','Separate task: compare two plans.'),('assistant','I compared the plans.')],1):
        rows.append({'evidence_id':f'id{i}','model_ref':f'm{i}','role':role,'text':text,'turn_id':f't{i}',
            'raw_line_sha256':f'hash{i}'})
    source={'status':'complete','thread_id':'test','messages':rows,'source_revision':revision_for_messages(rows),
            'source_files':['test.jsonl'],'source':'codex_thread_history'}
    episodes=[]
    for i,part in enumerate(partition_source(source,['id7'])):
        local=state_partition_source(source,part['_messages'],part['source_revision'])
        state=({'subject':{'text':'Document','message_ids':['id1']},
            'goal':{'text':'Retry creating the document after repeated timeouts.','message_ids':['id6']},
            'phase':'requested','constraints':[],'corrections':[],
            'assistant_reports':[{'text':'API 524 timeout.','message_ids':['id5']}],
            'unresolved':[{'text':'Retry creating the document.','message_ids':['id6']}]} if i==0 else {
            'subject':{'text':'Two plans','message_ids':['id7']},'goal':{'text':rows[6]['text'],'message_ids':['id7']},
            'phase':'assistant_reported','constraints':[],'corrections':[],'unresolved':[],
            'assistant_reports':[{'text':rows[7]['text'],'message_ids':['id8']}]})
        episodes.append({**{k:v for k,v in part.items() if k!='_messages'},'draft':validate_state_draft(local,state,model='old')})
    decisions=[{'message_id':m['evidence_id'],'decision':'new_episode' if m['evidence_id']=='id7' else 'same_episode',
        'method':'model_boundary_review'} for m in rows[1:] if m['role']=='user']
    bundle=validate_episode_bundle(source,{'schema':'evolving-profile.scenario-episode-bundle.v1','status':'source_linked_episode_draft',
        'thread_id':source['thread_id'],'parent_source_revision':source['source_revision'],'boundary_decisions':decisions,
        'unresolved_boundary_ids':[],'episodes':episodes})
    diagnostic={'source_revision':source['source_revision'],'bundle_sha256':fingerprint_episode_bundle(bundle),
        'reason':'user_intent_field_attribution_invalid','fields':[],'location':{'message_ref':'m3','intent_index':0,'link_index':0}}
    return source,bundle,diagnostic

def invoke(source,bundle,diagnostic,opener):
    from lib.scenario_attribution_repair import request_episode_bundle_attribution_repair
    return request_episode_bundle_attribution_repair(source,bundle,diagnostic,base_url='https://test.invalid',api_key='test',model='test',opener=opener)

def responder(source,bundle,calls,fields=None,mutate=None):
    def opener(request,timeout):
        calls.append(json.loads(request.data))
        answer={'source_revision':source['source_revision'],'bundle_sha256':fingerprint_episode_bundle(bundle),
            'focus_message_id':'id3','decision':'select' if fields else 'none','field_refs':fields or []}
        if mutate:mutate(answer)
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(answer)}}]}).encode())
    return opener

def test_semantic_selection_adds_only_focus_citation_to_existing_user_claims():
    source,bundle,diagnostic=fixture();before=copy.deepcopy(bundle);calls=[]
    result=invoke(source,bundle,diagnostic,responder(source,bundle,calls,['goal','unresolved/0']))
    assert len(calls)==1
    data=json.loads(calls[0]['messages'][1]['content'])
    assert [x['message_id'] for x in data['episode_messages']]==[f'id{i}' for i in range(1,7)]
    assert data['focus_message_id']=='id3'
    assert all(not x['field_ref'].startswith('assistant_reports') for x in data['user_fields'])
    old=before['episodes'][0]['draft']['state'];state=result['episodes'][0]['draft']['state']
    expected=copy.deepcopy(old);expected['goal']['message_ids'].append('id3');expected['unresolved'][0]['message_ids'].append('id3')
    assert state==expected
    assert result['episodes'][1]==before['episodes'][1]
    assert result['boundary_decisions']==before['boundary_decisions']
    assert result['episodes'][0]['draft']['summaries']=={k:v.replace('[来源:id6]','[来源:id6,id3]')
        for k,v in before['episodes'][0]['draft']['summaries'].items()}
    assert result['attribution_repair']['independent_review_required'] is True
    assert result['attribution_repair']['publication_performed'] is False
    assert fingerprint_episode_bundle(result)!=fingerprint_episode_bundle(before)
    assert bundle==before
    validate_episode_bundle(source,result)

def test_explicit_none_for_unrepresented_condition_returns_no_candidate():
    source,bundle,diagnostic=fixture('Use A4 paper and preserve every table.');before=copy.deepcopy(bundle);calls=[]
    assert invoke(source,bundle,diagnostic,responder(source,bundle,calls)) is None
    assert len(calls)==1 and bundle==before
    data=json.loads(calls[0]['messages'][1]['content'])
    assert data['focus_text']=='Use A4 paper and preserve every table.'
    assert all('A4' not in claim['text'] for claim in data['user_fields'])

@pytest.mark.parametrize('kind',['source','bundle','reason','focus_assistant','focus_foreign','fields','location','changed_source'])
def test_invalid_diagnostic_rejected_before_provider(kind):
    source,bundle,diagnostic=fixture()
    if kind=='source':diagnostic['source_revision']='old'
    if kind=='bundle':diagnostic['bundle_sha256']='old'
    if kind=='reason':diagnostic['reason']='user_intent_omitted'
    if kind=='focus_assistant':diagnostic['location']['message_ref']='m2'
    if kind=='focus_foreign':diagnostic['location']['message_ref']='m99'
    if kind=='fields':diagnostic['fields']=['invented']
    if kind=='location':diagnostic['location']['intent_index']=99
    if kind=='changed_source':source['messages'][2]['text']='different'
    def forbidden(*a,**kw):raise AssertionError('must fail before provider')
    with pytest.raises(ValueError):invoke(source,bundle,diagnostic,forbidden)

@pytest.mark.parametrize('kind',['assistant_field','foreign_field','source','bundle','focus','wording','duplicate_fields','none_with_fields','empty_select'])
def test_invalid_selection_never_updates_candidate_or_retries(kind):
    source,bundle,diagnostic=fixture();before=copy.deepcopy(bundle);calls=[]
    def mutate(answer):
        if kind=='assistant_field':answer['field_refs']=['assistant_reports/0']
        if kind=='foreign_field':answer['field_refs']=['constraints/99']
        if kind=='source':answer['source_revision']='wrong'
        if kind=='bundle':answer['bundle_sha256']='wrong'
        if kind=='focus':answer['focus_message_id']='id4'
        if kind=='wording':answer['text']='invented claim'
        if kind=='duplicate_fields':answer['field_refs']=['goal','goal']
        if kind=='none_with_fields':answer['decision']='none'
        if kind=='empty_select':answer['field_refs']=[]
    with pytest.raises(ValueError):invoke(source,bundle,diagnostic,responder(source,bundle,calls,['goal'],mutate))
    assert len(calls)==1 and bundle==before

def test_already_present_citation_cannot_count_as_new_draft():
    source,bundle,diagnostic=fixture();diagnostic['location']['message_ref']='m6';calls=[]
    with pytest.raises(ValueError):
        invoke(source,bundle,diagnostic,responder(source,bundle,calls,['goal'],lambda a:a.update(focus_message_id='id6')))
    assert len(calls)==1

def test_mutated_source_while_provider_runs_rejected():
    source,bundle,diagnostic=fixture();calls=[]
    def mutate(answer):source['messages'][2]['text']='changed'
    with pytest.raises(ValueError):invoke(source,bundle,diagnostic,responder(source,bundle,calls,['goal'],mutate))
    assert len(calls)==1

def test_citation_cardinality_is_not_relaxed(monkeypatch):
    from lib.scenario_state_v3 import STATE_LIMITS
    source,bundle,diagnostic=fixture();before=copy.deepcopy(bundle);calls=[]
    monkeypatch.setitem(STATE_LIMITS,'message_ids_max_per_claim',1)
    with pytest.raises(ValueError,match='citation_limit'):
        invoke(source,bundle,diagnostic,responder(source,bundle,calls,['goal']))
    assert len(calls)==1 and bundle==before

def test_full_input_over_budget_fails_without_clipping_or_provider(monkeypatch):
    from lib import scenario_attribution_repair as repair
    source,bundle,diagnostic=fixture();monkeypatch.setattr(repair,'MAX_INPUT_CHARS',100)
    def forbidden(*a,**kw):raise AssertionError('provider must not be called')
    with pytest.raises(ValueError,match='input_over_budget'):invoke(source,bundle,diagnostic,forbidden)

@pytest.mark.parametrize('mode',['truncated','invalid_json','oversize','duplicate_key'])
def test_invalid_response_is_terminal_and_does_not_retry(mode):
    from lib.scenario_attribution_repair import MAX_RESPONSE_BYTES
    source,bundle,diagnostic=fixture();calls=[]
    def opener(*args,**kwargs):
        calls.append(1)
        if mode=='oversize':return io.BytesIO(b' '* (MAX_RESPONSE_BYTES+1))
        if mode=='invalid_json':return io.BytesIO(b'{broken')
        body='{"decision":"none","decision":"select"}'
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'length' if mode=='truncated' else 'stop','message':{'content':body}}]}).encode())
    with pytest.raises(ValueError):invoke(source,bundle,diagnostic,opener)
    assert len(calls)==1

def test_caller_provider_budget_remains_authoritative():
    source,bundle,diagnostic=fixture();calls=[]
    def opener(*args,**kwargs):calls.append(1);raise ValueError('provider_budget_exhausted')
    with pytest.raises(ValueError,match='provider_budget_exhausted'):invoke(source,bundle,diagnostic,opener)
    assert len(calls)==1

def test_mutated_bundle_while_provider_runs_rejected():
    source,bundle,diagnostic=fixture();calls=[]
    def mutate(answer):bundle['episodes'][0]['draft']['state']['goal']['text']='changed'
    with pytest.raises(ValueError,match='source_changed'):
        invoke(source,bundle,diagnostic,responder(source,bundle,calls,['goal'],mutate))
    assert len(calls)==1
