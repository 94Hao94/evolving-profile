import copy
import importlib.util
import json
import os
from pathlib import Path
import pytest
from lib import scenario_source
from lib.context_incremental import _input_revision
from lib.scenario_checkpoint import _qualify_source

SID='513bccbd-4630-4257-b058-f16f8cb246b8'
def fixture(tmp_path,mode=None):
    home=tmp_path.resolve();base=home/'.evolving-profile/claude-code';base.mkdir(parents=True)
    legacy=Path(__file__).parent/'fixtures/desktop_rollout_legacy.py'
    (base/'desktop_rollout.py').write_bytes(legacy.read_bytes())
    spec=importlib.util.spec_from_file_location('fixture_legacy_rollout',legacy);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    root=home/'.claude/projects/project';root.mkdir(parents=True);native=root/(SID+'.jsonl')
    label='[Image: original 2000x1000, displayed at 1000x500.]'
    rows=[{'type':'user','sessionId':SID,'timestamp':'2026-10-25T01:00:00Z','message':{'role':'user','content':'请检查文件。'}},
        {'type':'assistant','sessionId':SID,'timestamp':'2026-10-25T01:01:00Z','message':{'role':'assistant','content':'助手报告正在检查。'}},
        {'type':'user','sessionId':SID,'isMeta':True,'turnCompanion':True,'uuid':'machine','message':{'role':'user','content':label}},
        {'type':'api-request-blob','sessionId':SID,'hash':'a'*64,'message':{'role':'user','content':label}},
        {'type':'assistant','sessionId':SID,'timestamp':'2026-10-25T01:02:00Z','message':{'role':'assistant','content':'助手报告已完成。'}}]
    if mode=='canonical_same':rows.insert(2,{'type':'user','sessionId':SID,'message':{'role':'user','content':label}})
    if mode=='queued_same':rows.insert(2,{'type':'attachment','sessionId':SID,'attachment':{'type':'queued_command','origin':{'kind':'human'},'humanTurn':True,'prompt':label}})
    if mode=='unmatched':rows[3]['message']['content']='The user sent a new message: keep my instruction.'
    native.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    mirror_root=base/'rollouts';mirror_root.mkdir();mirror=mirror_root/f'rollout-2026-10-25T01-00-00-{SID}.jsonl'
    generated,_=mod.build_rows(SID,'/project',mod.read_messages(native),host='claude-desktop')
    mirror.write_bytes(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in generated).encode())
    return home,native,mirror,mirror_root

def test_exact_proof_excludes_only_machine_replay_preserves_old_bytes_budget_and_checkpoint(tmp_path,monkeypatch):
    from lib import claude_mirror_context as helper
    home,native,mirror,root=fixture(tmp_path);before=mirror.read_bytes()
    proof=helper.machine_context_proof(mirror,SID,home=home)
    assert proof and len(proof['exclusions'])==1
    original=scenario_source.read_session_source(SID,root)
    monkeypatch.setattr(helper,'DEFAULT_HOME',home)
    filtered=scenario_source.read_session_source(SID,root)
    assert len(filtered['messages'])==len(original['messages'])-1
    assert filtered['source_files']==original['source_files']==[str(mirror)]
    assert _input_revision(filtered,'p','b')==_input_revision(original,'p','b')
    assert _qualify_source(filtered) is True
    assert mirror.read_bytes()==before
    for m in original['messages']:
        import hashlib
        with mirror.open('rb') as f:f.seek(m['byte_offset']);raw=f.readline()
        assert hashlib.sha256(raw).hexdigest()==m['raw_line_sha256']
    from lib.raw_session_evidence import read_evidence
    old_offset,old_hash=next(iter(proof['exclusions']))
    original=read_evidence(SID,root,cache_root=tmp_path/'locator-cache',raw_line_sha256=old_hash)
    assert original['status']=='source_read'
    assert original['source']['locators'][0]['byte_offset']==old_offset
    assert original['source']['locators'][0]['raw_line_sha256']==old_hash

@pytest.mark.parametrize('mode',['canonical_same','queued_same','unmatched'])
def test_human_same_body_or_unmatched_api_stays_semantic(tmp_path,mode):
    from lib.claude_mirror_context import machine_context_proof
    home,_,mirror,_=fixture(tmp_path,mode)
    proof=machine_context_proof(mirror,SID,home=home)
    assert proof is not None and proof['exclusions']=={}

@pytest.mark.parametrize('mode',['native_drift','mirror_drift','code_drift','missing','ambiguous','symlink'])
def test_unprovable_input_yields_no_exclusion(tmp_path,mode):
    from lib.claude_mirror_context import machine_context_proof
    home,native,mirror,_=fixture(tmp_path)
    if mode=='native_drift':
        old=native.stat();native.write_text(native.read_text()+'{}\n');os.utime(native,ns=(old.st_atime_ns,old.st_mtime_ns+2000000000))
    if mode=='mirror_drift':mirror.write_bytes(mirror.read_bytes()+b'\n')
    if mode=='code_drift':(home/'.evolving-profile/claude-code/desktop_rollout.py').write_text('# changed')
    if mode=='missing':native.unlink()
    if mode=='ambiguous':
        other=native.parent.parent/'other';other.mkdir();(other/native.name).write_bytes(native.read_bytes())
    if mode=='symlink':
        original=native.with_suffix('.backup');native.rename(original);native.symlink_to(original)
    assert machine_context_proof(mirror,SID,home=home) is None

def test_native_drift_restores_original_source_and_invalidates_old_review_revision(tmp_path,monkeypatch):
    from lib import claude_mirror_context as helper
    home,native,mirror,root=fixture(tmp_path);monkeypatch.setattr(helper,'DEFAULT_HOME',home)
    first=scenario_source.read_session_source(SID,root)
    assert any(x.get('metadata_kind')=='native_api_replay_machine_companion' for x in first['context_metadata_exclusions'])
    old=native.stat();native.write_text(native.read_text()+'{}\n');os.utime(native,ns=(old.st_atime_ns,old.st_mtime_ns+2000000000))
    current=scenario_source.read_session_source(SID,root)
    assert len(current['messages'])==len(first['messages'])+1
    assert current['source_revision']!=first['source_revision']
    assert _input_revision(first,'p','b')==_input_revision(current,'p','b')
    from lib.memory_recovery_scenario import publish_automated_session
    with pytest.raises(ValueError,match='automated_source_revision_changed'):
        publish_automated_session({},first,{}, {},{},root)

def test_inflight_native_drift_disables_exclusions(tmp_path,monkeypatch):
    from lib import claude_mirror_context as helper
    home,native,mirror,_=fixture(tmp_path);original=helper._encode;changed=[]
    def encode(row):
        if not changed:
            changed.append(True);native.write_text(native.read_text()+'{}\n')
        return original(row)
    monkeypatch.setattr(helper,'_encode',encode)
    assert helper.machine_context_proof(mirror,SID,home=home) is None

def test_real_513_has_exact_proof_and_real_mirror_is_read_only():
    if os.environ.get('EP_TEST_REAL_CLAUDE_SOURCE')!='1':pytest.skip('optional real local source audit')
    from lib.claude_mirror_context import machine_context_proof
    root=Path.home()/'.evolving-profile/claude-code/rollouts'
    paths=list(root.rglob('*'+SID+'.jsonl'))
    if len(paths)!=1:pytest.skip('local real fixture unavailable')
    before=paths[0].read_bytes();proof=machine_context_proof(paths[0],SID)
    assert proof and len(proof['exclusions'])==2
    assert paths[0].read_bytes()==before

def test_dot_traversal_cannot_escape_trusted_mirror_root(tmp_path):
    from lib.claude_mirror_context import machine_context_proof
    home,_,mirror,root=fixture(tmp_path)
    escaped=root.parent/'outside.jsonl';escaped.write_bytes(mirror.read_bytes())
    assert machine_context_proof(root/'..'/escaped.name,SID,home=home) is None
