import copy
import hashlib
import json
from pathlib import Path
import pytest
from test_scenario_native_form import fixture
from lib.scenario_source import read_session_source,revision_for_messages
from lib.scenario_checkpoint import _qualify_source
from lib.context_incremental import _input_revision

def test_proven_native_form_preserves_original_role_for_strict_checkpoint(tmp_path):
    source,_,_=fixture(tmp_path)
    assert _qualify_source(source) is True
    row=next(r for r in source['context_metadata_exclusions'] if r['metadata_kind']=='native_form_question_context')
    assert row['original_role']=='user'

def test_actual_current_session_passes_strict_checkpoint_without_provider():
    session='01a176a4-6baf-7ca2-bbdd-716e733b5229'
    source=read_session_source(session,Path.home()/'.codex/sessions',max_chars=60000)
    if source['status']!='complete':pytest.skip('local real source unavailable or over budget')
    assert any(r.get('metadata_kind')=='native_form_question_context' for r in source['context_metadata_exclusions'])
    assert _qualify_source(source) is True

@pytest.mark.parametrize('mutation',['role','hash'])
def test_raw_role_and_hash_tampering_still_fail_checkpoint(tmp_path,mutation):
    source,path,_=fixture(tmp_path);target=source['messages'][-1]
    with path.open('rb') as f:f.seek(target['byte_offset']);raw=f.readline()
    if mutation=='role':
        row=json.loads(raw);row['payload']['role']='assistant';changed=(json.dumps(row,ensure_ascii=False)+'\n').encode()
        original=path.read_bytes();path.write_bytes(original[:target['byte_offset']]+changed+original[target['byte_offset']+len(raw):])
        digest=hashlib.sha256(changed).hexdigest()
    else:digest='0'*64
    for row in source['messages']+source['context_metadata_exclusions']:
        if row['byte_offset']==target['byte_offset']:row['raw_line_sha256']=digest
    source['source_revision']=revision_for_messages(source['messages'],source['context_metadata_exclusions'])
    with pytest.raises(ValueError,match='scenario_checkpoint_source_changed'):_qualify_source(source)

def test_metadata_fix_changes_review_binding_but_not_semantic_attempt_budget(tmp_path):
    source,_,_=fixture(tmp_path);legacy=copy.deepcopy(source)
    for row in legacy['context_metadata_exclusions']:
        if row.get('metadata_kind')=='native_form_question_context':row.pop('original_role',None)
    legacy['source_revision']=revision_for_messages(legacy['messages'],legacy['context_metadata_exclusions'])
    assert source['source_revision']!=legacy['source_revision']
    assert _input_revision(source,'project','bank')==_input_revision(legacy,'project','bank')
