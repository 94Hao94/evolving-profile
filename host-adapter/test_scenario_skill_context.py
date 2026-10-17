"""Native paired Skill definitions are references, never a new human goal."""
import json
import uuid

import pytest
from lib.scenario_source import read_session_source
from lib.context_incremental import _input_revision


def source_fixture(tmp_path, envelope=None, *, name='other-skill', path='/skills/other-skill/SKILL.md', turn='t1', intervening=False):
    sid=str(uuid.uuid4())
    body=envelope if envelope is not None else f'<skill>\n<name>{name}</name>\n<path>{path}</path>\n---\nname: {name}\ndescription: General task support.\n---\n\n# Instructions\nUse a careful workflow.\n</skill>'
    rows=[{'type':'session_meta','payload':{'id':sid}},
          {'type':'turn_context','payload':{'turn_id':'t1'}},
          {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':f'[${name}]({path}) Rewrite this document; do not publish.'}]}}]
    if intervening:rows.append({'type':'response_item','payload':{'type':'message','role':'assistant','phase':'final_answer','content':[{'type':'output_text','text':'A separate answer.'}]}})
    if turn!='t1':rows.append({'type':'turn_context','payload':{'turn_id':turn}})
    rows.append({'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':body}]}})
    target=tmp_path/f'rollout-2026-10-15T10-00-00-{sid}.jsonl'
    target.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    return read_session_source(sid,tmp_path,max_chars=20000),body,target


@pytest.mark.parametrize('name,path',[('other-skill','/skills/other-skill/SKILL.md'),('通用技能',r'C:\skills\通用技能\SKILL.md')])
def test_paired_native_definition_does_not_replace_user_goal_and_retains_locator(tmp_path,name,path):
    source,body,target=source_fixture(tmp_path,name=name,path=path)
    assert source['user_count']==1
    assert source['messages'][-1]['text'].endswith('Rewrite this document; do not publish.')
    excluded=source['context_metadata_exclusions'][0]
    assert excluded['metadata_kind']=='native_paired_skill_definition'
    assert excluded['fact_authority']=='none'
    assert excluded['raw_line_sha256'] and excluded['source_path']==str(target)
    assert excluded['paired_user_evidence_id']==source['messages'][0]['evidence_id']
    with target.open('rb') as stream:
        stream.seek(excluded['byte_offset'])
        assert json.loads(stream.readline())['payload']['content'][0]['text']==body


@pytest.mark.parametrize('kind',['mixed','quoted','malformed','different_name','different_path','unknown_schema','different_turn','intervening'])
def test_uncertain_or_unpaired_definitions_remain_user_source(tmp_path,kind):
    body='<skill>\n<name>other-skill</name>\n<path>/skills/other-skill/SKILL.md</path>\n---\nname: other-skill\ndescription: General task support.\n---\n\n# Instructions\nUse a careful workflow.\n</skill>'
    if kind=='mixed':body+='\nDo not overwrite my document.'
    if kind=='quoted':body='```xml\n'+body+'\n```'
    if kind=='malformed':body=body.replace('</skill>','')
    if kind=='different_name':body=body.replace('name: other-skill','name: unrelated')
    if kind=='different_path':body=body.replace('/skills/other-skill/','/other/')
    if kind=='unknown_schema':body=body.replace('<name>','<name extra="unknown">')
    source,_,_=source_fixture(tmp_path,body,turn='t2' if kind=='different_turn' else 't1',intervening=kind=='intervening')
    assert source['messages'][-1]['text']==body.strip()
    assert not source['context_metadata_exclusions']


def test_classification_changes_review_revision_without_buying_new_model_attempts(tmp_path):
    source,body,_=source_fixture(tmp_path)
    excluded=source['context_metadata_exclusions'][0]
    original=[*source['messages'],{'role':'user','text':body,'turn_id':'t1','evidence_id':excluded['evidence_id']}]
    old={**source,'messages':original}
    old.pop('_budget_messages',None)
    assert _input_revision(source,'project','bank')==_input_revision(old,'project','bank')
    from lib.scenario_source import revision_for_messages
    assert source['source_revision']!=revision_for_messages(original)


def test_multiple_envelopes_cannot_hide_intervening_human_prohibition(tmp_path):
    definition='<skill>\n<name>other-skill</name>\n<path>/skills/other-skill/SKILL.md</path>\n---\nname: other-skill\ndescription: General task support.\n---\nWorkflow.\n</skill>'
    text=definition+'\nDo not overwrite my original; compare only.\n'+definition.replace('other-skill','uninvoked')
    source,_,_=source_fixture(tmp_path,text)
    assert source['messages'][-1]['text']==text
    assert not source['context_metadata_exclusions']


def test_native_crlf_definition_uses_the_same_structural_contract(tmp_path):
    definition='<skill>\n<name>other-skill</name>\n<path>/skills/other-skill/SKILL.md</path>\n---\nname: other-skill\ndescription: General task support.\n---\nWorkflow.\n</skill>'
    source,_,_=source_fixture(tmp_path,definition.replace('\n','\r\n'))
    assert source['user_count']==1
    assert source['context_metadata_exclusions'][0]['metadata_kind']=='native_paired_skill_definition'
