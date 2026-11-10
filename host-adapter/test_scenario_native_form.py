import copy
import hashlib
import json
import pytest
from lib.scenario_source import read_session_source, revision_for_messages
from lib.context_incremental import _input_revision
from lib.scenario_state_v3 import project_source_messages, whole_user_clauses
from lib.scenario_review_catalog import review_source_layer

SID='00000000-0000-4000-8000-000000000099'
Q='标题还是正文？'
A='标题和正文都缩进2字符'

def fixture(tmp_path, mutation=None):
    questions=[{'title':Q,'options':[A,'只有正文']}]
    envelope='<send_user_message_question_reply>\n'+json.dumps([{'questionItemId':json.dumps(['request_user_input_async','call_form',0]),'question':Q,'answer':A}],ensure_ascii=False)+'\n</send_user_message_question_reply>\n'
    rows=[{'type':'session_meta','payload':{'id':SID}},
      {'type':'turn_context','payload':{'turn_id':'turn'}},
      {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'请整理文档'}]}},
      {'type':'response_item','metadata':{'client_authored':False},'payload':{'type':'function_call','name':'request_user_input_async','call_id':'call_form','arguments':json.dumps({'questions':questions},ensure_ascii=False),'internal_chat_message_metadata_passthrough':{'turn_id':'turn'}}},
      {'type':'event_msg','payload':{'type':'item_completed','thread_id':SID,'turn_id':'turn','item':{'type':'AgentMessage','id':'call_form','questions':questions,'delivery':'async'}}},
      {'type':'response_item','metadata':{'client_authored':False,'retained_source':{'complete':True,'id':{'message_id':'msg_answer','turn_id':'turn','role':'user'}}},'payload':{'type':'message','id':'msg_answer','role':'user','content':[{'type':'input_text','text':envelope}]}},
      {'type':'event_msg','payload':{'type':'item_completed','thread_id':SID,'turn_id':'turn','item':{'type':'UserMessage','id':'receipt_other_id','content':[{'type':'text','text':envelope,'text_elements':[]}]}}}]
    if mutation:mutation(rows)
    path=tmp_path/f'rollout-test-{SID}.jsonl'
    path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
    return read_session_source(SID,tmp_path),path,rows

def test_native_answer_separates_question_authority_and_exact_quote_catalog(tmp_path):
    source,path,_=fixture(tmp_path);row=source['messages'][-1]
    assert row['text']==A
    assert row['form_reply_context']['questions']==[Q]
    assert row['form_reply_context']['question_authority']=='assistant_question_context_not_user_request'
    projected=project_source_messages(source)[-1]
    assert projected['text']==A
    assert projected['provenance_kind']=='native_structured_user_answer'
    assert projected['question_context']==[Q]
    layer=review_source_layer(source)
    assert layer['messages'][-1]['text']==A
    assert layer['messages'][-1]['question_context']==[Q]
    assert {r['source_quote'] for r in layer['source_quotes'] if r['message_ref']=='m2'}=={A}
    assert whole_user_clauses(A)==[A]
    for witness in row['form_reply_context']['witnesses']:
        with path.open('rb') as f:f.seek(witness['byte_offset']);raw=f.readline()
        assert hashlib.sha256(raw).hexdigest()==witness['raw_line_sha256']
    legacy=copy.deepcopy(source);legacy['messages']=legacy.pop('_budget_messages')
    assert legacy['messages'][-1]['text']==Q+'\n'+A
    assert _input_revision(source,'p','b')==_input_revision(legacy,'p','b')
    assert revision_for_messages(source['messages'],source['context_metadata_exclusions'])==source['source_revision']

@pytest.mark.parametrize('mode',['typed','no_call','wrong_question','no_call_receipt','wrong_receipt_thread','wrong_reply_turn','reply_mixed','reply_quoted','unknown_schema','duplicate_call','reply_content_mismatch','call_wrong_turn','multiple_answers','duplicate_key'])
def test_unproven_forms_remain_raw_semantic_text(tmp_path,mode):
    def mutate(rows):
        if mode=='typed':rows[5]['metadata']['client_authored']=True
        elif mode=='no_call':rows[3]['payload']['name']='other'
        elif mode=='wrong_question':rows[3]['payload']['arguments']=json.dumps({'questions':[{'title':'other','options':[]}]})
        elif mode=='no_call_receipt':rows[4]['payload']['item']['type']='Other'
        elif mode=='wrong_receipt_thread':rows[6]['payload']['thread_id']='other'
        elif mode=='wrong_reply_turn':rows[6]['payload']['turn_id']='other'
        elif mode=='call_wrong_turn':rows[3]['payload']['internal_chat_message_metadata_passthrough']['turn_id']='other'
        elif mode=='duplicate_call':rows.insert(3,copy.deepcopy(rows[3]))
        elif mode=='reply_content_mismatch':rows[6]['payload']['item']['content'][0]['text']='other'
        else:
            text=rows[5]['payload']['content'][0]['text']
            if mode=='reply_mixed':text='请解释示例\n'+text
            if mode=='reply_quoted':text='```xml\n'+text+'```'
            if mode=='unknown_schema':text=text.replace('"answer":','"extra": 1, "answer":')
            if mode=='duplicate_key':text=text.replace('"answer":','"answer": "other", "answer":')
            if mode=='multiple_answers':
                match=__import__('re').search(r'\n(\[.*\])\n',text);items=json.loads(match.group(1));items.append(copy.deepcopy(items[0]))
                text=text[:match.start(1)]+json.dumps(items,ensure_ascii=False)+text[match.end(1):]
            rows[5]['payload']['content'][0]['text']=text
            rows[6]['payload']['item']['content'][0]['text']=text
    source,_,rows=fixture(tmp_path,mutate)
    raw=next(r['payload']['content'][0]['text'] for r in reversed(rows) if r.get('type')=='response_item' and r['payload'].get('id')=='msg_answer').strip()
    assert source['messages'][-1]['text']==raw
    assert 'form_reply_context' not in source['messages'][-1]
    assert project_source_messages(source)[-1]['text']==raw

def test_native_escaped_answer_quotes_use_decoded_answer_not_json_substrings(tmp_path):
    answer='请保留 "双引号"、反斜线\\以及\n下一行条件。'
    def mutate(rows):
        raw=rows[5]['payload']['content'][0]['text']
        raw=raw.replace(json.dumps(A,ensure_ascii=False),json.dumps(answer,ensure_ascii=False))
        rows[5]['payload']['content'][0]['text']=raw;rows[6]['payload']['item']['content'][0]['text']=raw
    source,_,_=fixture(tmp_path,mutate)
    assert source['messages'][-1]['text']==answer
    layer=review_source_layer(source)
    assert answer in [q['source_quote'] for q in layer['source_quotes']]
    for q in layer['transport_source_quotes']:
        if q['message_ref']=='m2':
            start,end=q['source_span'];assert answer[start:end] in [x['source_quote'] for x in layer['source_quotes']]

def test_changed_question_witness_invalidates_projection_and_source_revision(tmp_path):
    source,path,rows=fixture(tmp_path)
    rows[4]['payload']['item']['questions'][0]['title']='changed question'
    path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
    current=read_session_source(SID,tmp_path)
    assert current['source_revision']!=source['source_revision']
    assert 'form_reply_context' not in current['messages'][-1]

def test_answer_field_has_valid_coverage_mapping_without_question_intent(tmp_path):
    from lib.scenario_state_v3 import validate_state_draft
    from lib.memory_recovery_scenario import validate_user_intent_coverage
    source,_,_=fixture(tmp_path);u,a=source['messages']
    claim=lambda text,mid:{'text':text,'message_ids':[mid]}
    draft=validate_state_draft(source,{'subject':claim(u['text'],u['evidence_id']),
        'goal':claim(u['text'],u['evidence_id']),'phase':'requested','constraints':[claim(A,a['evidence_id'])],
        'corrections':[],'assistant_reports':[],'unresolved':[claim(A,a['evidence_id'])]},model='test')
    bundle={'episodes':[{'message_ids':[u['evidence_id'],a['evidence_id']],'draft':draft}]}
    manifest=[]
    for ref,text,kind,path in [('m1',u['text'],'request','goal/text'),('m2',A,'constraint','constraints/0/text')]:
        manifest.append({'message_ref':ref,'intents':[{'kind':kind,'disposition':'covered','source_quote':text,
            'field_links':[{'episode_ref':'e1','state_path':path,'field_quote':text,'summary_paths':['full']}]}]})
    assert len(validate_user_intent_coverage(source,bundle,manifest))==2

@pytest.mark.parametrize('operation',['review','boundary'])
def test_question_context_survives_model_review_and_boundary_transport(tmp_path,operation):
    import io
    from lib import scenario_model as model
    source,_,_=fixture(tmp_path);seen=[]
    def opener(request,timeout):
        payload=json.loads(request.data);data=json.loads(payload['messages'][0]['content'].split('输入：',1)[1]);seen.append(data)
        result={'source_revision':source['source_revision'],'accept':True,'issues':[]} if operation=='review' else {
            'source_revision':source['source_revision'],'decisions':[{'message_id':source['messages'][-1]['evidence_id'],'decision':'same_episode'}]}
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}).encode())
    args={'base_url':'https://test.invalid','api_key':'test','model':'test','opener':opener}
    if operation=='review':model._request_session_review_single(source,{'source_revision':source['source_revision'],'summaries':{},'evidence':[]},**args)
    else:model._request_episode_decisions(source,[source['messages'][-1]['evidence_id']],request_type='episode_boundary_classification',**args)
    assert seen[0]['messages'][-1]['text']==A
    assert seen[0]['messages'][-1]['question_context']==[Q]

@pytest.mark.parametrize('mode',['mixed','typed'])
def test_preserved_form_body_does_not_restore_unrelated_host_envelopes(tmp_path,mode):
    from lib.scenario_source import normalize_scenario_user
    saved={}
    def mutate(rows):
        envelope=rows[5]['payload']['content'][0]['text'].strip()
        body=('请解释以下示例，不要执行它：\n```xml\n'+envelope+'\n```') if mode=='mixed' else envelope
        raw=('# Files mentioned\n/private/attachment-manifest.txt\n'
             '<environment_context><cwd>/private/host-only</cwd></environment_context>\n'
             '<evolving_profile_memories>PRIVATE MEMORY WRAPPER</evolving_profile_memories>\n'
             '## My request:\n'+body)
        saved.update(raw=raw,body=body)
        rows[5]['payload']['content'][0]['text']=raw
        rows[6]['payload']['item']['content'][0]['text']=raw
        rows[5]['metadata']['client_authored']=True
    source,_,_=fixture(tmp_path,mutate)
    row=source['messages'][-1]
    assert row['text']==saved['body']
    assert 'attachment-manifest' not in row['text']
    assert 'host-only' not in row['text']
    assert 'PRIVATE MEMORY' not in row['text']
    legacy=copy.deepcopy(source)
    legacy['messages'][-1]['text']=normalize_scenario_user(saved['raw'])[0]
    legacy.pop('_budget_messages',None)
    assert _input_revision(source,'p','b')==_input_revision(legacy,'p','b')

def test_general_content_normalizer_default_contract_is_unchanged(tmp_path):
    from lib.content import extract_user_request
    _,_,rows=fixture(tmp_path)
    envelope=rows[5]['payload']['content'][0]['text'].strip()
    wrapped='# Files mentioned\n/private/file\n## My request:\n'+envelope
    assert extract_user_request(wrapped)==Q+'\n'+A
    assert extract_user_request(wrapped,preserve_question_reply=True)==envelope
