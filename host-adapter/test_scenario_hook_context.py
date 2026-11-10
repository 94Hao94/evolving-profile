"""Only an exact native HookPrompt event proves a Stop envelope is host context."""
import copy
import hashlib
import json

import pytest

from lib.context_incremental import _input_revision
from lib.scenario_source import read_session_source, revision_for_messages

SID = '00000000-0000-4000-8000-000000000082'
RUN = 'stop:6:/Users/example/.codex/hooks.json'
BODY = 'Runtime check: inspect the existing scope before ending this turn.'
ENVELOPE = f'<hook_prompt hook_run_id="{RUN}">{BODY}</hook_prompt>'


def fixture(tmp_path, mutation=None):
    def msg(role, text, mid):
        return {'type': 'response_item', 'payload': {'type': 'message', 'id': mid,
            'role': role, **({'phase': 'final_answer'} if role=='assistant' else {}),
            'content': [{'type': 'input_text' if role=='user' else 'output_text', 'text': text}]}}
    rows = [{'type': 'session_meta', 'payload': {'id': SID}},
            {'type': 'turn_context', 'payload': {'turn_id': 't1'}},
            msg('user', 'Check my document; do not publish it.', 'human'),
            msg('assistant', 'I checked the document.', 'answer'),
            msg('user', ENVELOPE, 'hook-message'),
            {'type': 'event_msg', 'payload': {'type': 'item_completed', 'thread_id': SID,
                'turn_id': 't1', 'item': {'type': 'HookPrompt', 'id': 'hook-message',
                    'fragments': [{'text': BODY, 'hookRunId': RUN}]}}},
            msg('assistant', 'The runtime check is complete.', 'followup')]
    if mutation:mutation(rows)
    path=tmp_path/f'rollout-test-{SID}.jsonl'
    path.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows))
    return read_session_source(SID,tmp_path),path


def test_native_stop_hook_is_context_not_an_independent_user_intent(tmp_path):
    source,path=fixture(tmp_path)
    assert [row['role'] for row in source['messages']]==['user','assistant','assistant']
    assert source['user_count']==1
    excluded=source['context_metadata_exclusions'][0]
    assert excluded['metadata_kind']=='native_stop_hook_prompt'
    assert excluded['fact_authority']=='none'
    assert excluded['original_role']=='user'
    assert excluded['excluded_from_semantic_input'] is True
    assert excluded['host_event']['message_id']=='hook-message'
    assert excluded['host_event']['hook_run_id']==RUN
    with path.open('rb') as stream:
        stream.seek(excluded['byte_offset']);raw=stream.readline()
        assert hashlib.sha256(raw).hexdigest()==excluded['raw_line_sha256']
        assert json.loads(raw)['payload']['content'][0]['text']==ENVELOPE
        stream.seek(excluded['host_event']['byte_offset']);event=stream.readline()
        assert hashlib.sha256(event).hexdigest()==excluded['host_event']['raw_line_sha256']
        assert json.loads(event)['payload']['item']['type']=='HookPrompt'


def test_hook_classification_invalidates_review_without_resetting_attempt_budget(tmp_path):
    source,_=fixture(tmp_path)
    assert '_budget_messages' in source
    legacy={**source,'messages':source['_budget_messages']}
    legacy.pop('_budget_messages')
    assert [row['role'] for row in legacy['messages']]==['user','assistant','user','assistant']
    assert _input_revision(legacy,'project','bank')==_input_revision(source,'project','bank')
    assert source['source_revision']!=revision_for_messages(legacy['messages'])


@pytest.mark.parametrize('kind',[
    'unpaired','wrong_message','wrong_turn','wrong_session','wrong_type','wrong_event',
    'wrong_body','wrong_run','multiple_fragments','extra_fragment_field','extra_attribute',
    'quoted','mixed_prefix','mixed_suffix','nested','unknown_hook','missing_message_id',
    'multiple_content_blocks','not_after_assistant','different_prior_turn','intervening_event'])
def test_unproven_or_mixed_hook_like_text_remains_semantic_source(tmp_path,kind):
    def mutate(rows):
        message=rows[4]['payload'];event=rows[5]['payload'];item=event['item'];fragment=item['fragments'][0]
        if kind=='unpaired':rows.pop(5)
        elif kind=='wrong_message':item['id']='other-message'
        elif kind=='wrong_turn':event['turn_id']='other-turn'
        elif kind=='wrong_session':event['thread_id']='other-session'
        elif kind=='wrong_type':item['type']='UserMessage'
        elif kind=='wrong_event':event['type']='item_started'
        elif kind=='wrong_body':fragment['text']='A different runtime prompt.'
        elif kind=='wrong_run':fragment['hookRunId']='stop:7:/Users/example/.codex/hooks.json'
        elif kind=='multiple_fragments':item['fragments'].append(copy.deepcopy(fragment))
        elif kind=='extra_fragment_field':fragment['unknown']='unrecognized-schema'
        elif kind=='extra_attribute':message['content'][0]['text']=ENVELOPE.replace('hook_run_id=', 'extra="x" hook_run_id=')
        elif kind=='quoted':message['content'][0]['text']='```xml\n'+ENVELOPE+'\n```'
        elif kind=='mixed_prefix':message['content'][0]['text']='Please explain this:\n'+ENVELOPE
        elif kind=='mixed_suffix':message['content'][0]['text']=ENVELOPE+'\nDo not edit my files.'
        elif kind=='nested':message['content'][0]['text']=ENVELOPE.replace(BODY,ENVELOPE);fragment['text']=ENVELOPE
        elif kind=='unknown_hook':message['content'][0]['text']=ENVELOPE.replace('stop:','other:');fragment['hookRunId']=RUN.replace('stop:','other:')
        elif kind=='missing_message_id':message.pop('id')
        elif kind=='multiple_content_blocks':message['content'].append({'type':'input_text','text':'Human follow-up.'})
        elif kind=='not_after_assistant':rows[3]= {'type':'turn_context','payload':{'turn_id':'t1'}}
        elif kind=='different_prior_turn':rows.insert(4,{'type':'turn_context','payload':{'turn_id':'t2'}});event['turn_id']='t2'
        elif kind=='intervening_event':rows.insert(5,{'type':'event_msg','payload':{'type':'unknown'}})
    source,_=fixture(tmp_path,mutate)
    assert source['user_count']==2
    assert not source['context_metadata_exclusions']
