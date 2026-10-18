"""Archive moves must preserve source identity, not manufacture model retries."""
import json
import shutil
import uuid
import copy
import pytest

from lib.scenario_source import read_session_source
from lib.context_incremental import ContextIncremental
from lib.raw_session_evidence import read_evidence
from test_context_incremental import rollout
from lib.context_summary import read_context_index,write_context_index
from test_context_semantic_reuse import accepted
from test_context_reuse_metadata import accepted_with_missing_metadata


def test_archive_move_keeps_exact_messages_revision_and_raw_locations(tmp_path):
    sid=str(uuid.uuid4());root=tmp_path/'sessions'
    path=rollout(root,sid,text='Keep this original instruction.')
    before=read_session_source(sid,root)
    archive=tmp_path/'archived_sessions';archive.mkdir()
    moved=archive/path.name;path.rename(moved)
    after=read_session_source(sid,root)
    assert after['status']=='complete'
    assert after['source_revision']==before['source_revision']
    assert [m['text'] for m in after['messages']]==['Keep this original instruction.']
    assert after['messages'][0]['source_path']==str(moved)
    assert read_evidence(sid,root,cache_root=tmp_path/'cache')['source']['locators'][0]['source_path']==str(moved)


def test_discovery_includes_archived_sources_but_preserves_new_after_filter(tmp_path):
    root=tmp_path/'sessions';root.mkdir();archive=tmp_path/'archived_sessions'
    current=str(uuid.uuid4());old=str(uuid.uuid4())
    rollout(archive,current)
    rollout(archive,old,created_at='2026-01-01T00:00:00Z')
    pipeline=ContextIncremental(tmp_path/'state',root,new_after='2026-10-08T00:00:00Z')
    assert pipeline.discover(now=100)['discovered']==1
    with pipeline.db() as db:
        assert [r['session_id'] for r in db.execute('SELECT * FROM jobs')]==[current]


def test_identical_active_archive_copies_do_not_duplicate_source_messages(tmp_path):
    sid=str(uuid.uuid4());root=tmp_path/'sessions';path=rollout(root,sid,text='One original message.')
    archive=tmp_path/'archived_sessions';archive.mkdir();shutil.copy2(path,archive/path.name)
    result=read_session_source(sid,root)
    assert result['status']=='complete'
    assert len(result['messages'])==1
    assert result['source_files']==[str(path)]
    raw=read_evidence(sid,root,cache_root=tmp_path/'cache')
    assert len(raw['source']['locators'])==1


def test_conflicting_copies_are_not_concatenated_or_selected_as_truth(tmp_path):
    sid=str(uuid.uuid4());root=tmp_path/'sessions';rollout(root,sid,text='Version one.')
    rollout(tmp_path/'archived_sessions',sid,text='A different version.')
    source=read_session_source(sid,root)
    assert source['status']=='source_ambiguous' and source['messages']==[]
    raw=read_evidence(sid,root,cache_root=tmp_path/'cache')
    assert raw['status']=='source_ambiguous' and raw['source']=={}


def test_archive_filename_does_not_override_native_session_identity(tmp_path):
    sid=str(uuid.uuid4());path=rollout(tmp_path/'archived_sessions',sid)
    lines=path.read_text().splitlines();meta=json.loads(lines[0]);meta['payload']['id']=str(uuid.uuid4())
    lines[0]=json.dumps(meta);path.write_text('\n'.join(lines)+'\n')
    result=read_session_source(sid,tmp_path/'sessions')
    assert result['status']=='source_identity_mismatch' and result['messages']==[]


def test_custom_source_root_does_not_read_unrelated_sibling_archive(tmp_path):
    sid=str(uuid.uuid4());rollout(tmp_path/'archived_sessions',sid)
    result=read_session_source(sid,tmp_path/'custom-selected-folder')
    assert result['status']=='source_missing'


def test_discovery_archive_move_preserves_failed_attempt_budget(tmp_path):
    sid=str(uuid.uuid4());root=tmp_path/'sessions';path=rollout(root,sid)
    pipeline=ContextIncremental(tmp_path/'state',root);pipeline.discover(now=100)
    for now in (200,2000,4000):
        pipeline.fail(pipeline.claim(now=now),'scenario_model_response_incomplete',now=now)
    archive=tmp_path/'archived_sessions';archive.mkdir();path.rename(archive/path.name)
    assert pipeline.discover(now=5000)['discovered']==1
    with pipeline.db() as db:
        job=dict(db.execute('SELECT * FROM jobs WHERE session_id=?',(sid,)).fetchone())
    assert job['attempts']==3
    assert job['source_check_pending']==1


def test_temporary_conflicting_copy_cannot_grant_a_fourth_provider_attempt(tmp_path):
    sid=str(uuid.uuid4());root=tmp_path/'sessions';rollout(root,sid)
    p=ContextIncremental(tmp_path/'state',root);p.discover(now=100);calls=[]
    def invalid(*_):calls.append(1);raise ValueError('scenario_state_invalid')
    for now in (200,1000,2000):p.run_once({},now=now,processor=invalid)
    other=rollout(tmp_path/'archived_sessions',sid,text='Conflicting copy.')
    p.discover(now=3000)
    assert p.run_once({},now=3100,processor=invalid)['status']=='waiting_source'
    other.unlink();p.discover(now=4000)
    p.run_once({},now=4100,processor=invalid)
    assert len(calls)==3
    with p.db() as db:assert db.execute('SELECT attempts FROM jobs').fetchone()[0]==3


def test_archiving_reviewed_source_reuses_summary_without_new_model(tmp_path,monkeypatch):
    p,path,row=accepted(tmp_path,monkeypatch);p.discover(now=100)
    def forbidden(*_):raise AssertionError('A location move cannot require model review')
    assert p.run_once({},now=200,processor=forbidden)['status']=='complete'
    archive=path.parent.parent/'archived_sessions';archive.mkdir();path.rename(archive/path.name)
    p.discover(now=300);result=p.run_once({},now=400,processor=forbidden)
    assert result['status']=='complete' and result['summary_reused'] is True
    current=read_context_index(p.index)['sessions'][0]
    assert current['summary']==row['summary']
    assert current['automated_source_coverage']==row['automated_source_coverage']
    assert current['source_location_projection']['current_source_files']==[str(archive/path.name)]
    (archive/path.name).rename(path)
    p.discover(now=500);assert p.run_once({},now=600,processor=forbidden)['status']=='complete'
    assert read_context_index(p.index)['sessions'][0]['source_location_projection']['current_source_files']==[str(path)]


def test_archive_relocation_preserves_review_binding_with_context_metadata(tmp_path):
    root,path,source,row=accepted_with_missing_metadata(tmp_path)
    p=ContextIncremental(tmp_path/'state',root,bank_id='bank-a');write_context_index(p.index,[row],[])
    def forbidden(*_):raise AssertionError('Unchanged original bytes cannot reach provider')
    assert p.run_once({},now=200,processor=forbidden)['status']=='idle'
    p.discover(now=300);assert p.run_once({},now=400,processor=forbidden)['status']=='complete'
    archive=root.parent/'archived_sessions';archive.mkdir();path.rename(archive/path.name)
    p.discover(now=500);result=p.run_once({},now=600,processor=forbidden)
    assert result['status']=='complete' and result['summary_reused'] is True
    current=read_context_index(p.index)['sessions'][0]
    assert current['source_revision']==row['source_revision']
    assert current['automated_source_coverage']==row['automated_source_coverage']
    assert current['context_metadata_exclusions']==source['context_metadata_exclusions']


@pytest.mark.parametrize('mutation',['text','review','outside_archive'])
def test_location_alias_does_not_mask_changed_source_or_rejected_review(tmp_path,mutation):
    from lib.memory_recovery_scenario import complete_same_source_metadata
    root,path,source,row=accepted_with_missing_metadata(tmp_path)
    original=copy.deepcopy(row)
    archive=root.parent/('unrelated-folder' if mutation=='outside_archive' else 'archived_sessions')
    archive.mkdir();moved=archive/path.name;path.rename(moved)
    if mutation=='text':
        text=moved.read_text();moved.write_text(text.replace('historical-page','changed-page'))
    if mutation=='review':row['automated_source_coverage']['accept']=False
    live=read_session_source(row['session_id'],root if mutation!='outside_archive' else archive)
    assert complete_same_source_metadata(row,live) is None
    if mutation!='review':assert row==original


def test_identity_mismatch_then_restore_cannot_renew_exhausted_budget(tmp_path):
    sid=str(uuid.uuid4());root=tmp_path/'sessions';path=rollout(root,sid)
    p=ContextIncremental(tmp_path/'state',root);p.discover(now=100);calls=[]
    def invalid(*_):calls.append(1);raise ValueError('scenario_state_invalid')
    for now in (200,1000,2000):p.run_once({},now=now,processor=invalid)
    other=rollout(tmp_path/'archived_sessions',sid)
    text=other.read_text();other.write_text(text.replace(sid,str(uuid.uuid4())))
    p.discover(now=3000)
    assert p.run_once({},now=3100,processor=invalid)['status']=='waiting_source'
    other.unlink();p.discover(now=4000)
    p.run_once({},now=4100,processor=invalid)
    assert len(calls)==3


@pytest.mark.parametrize('metadata',[False,True])
def test_public_summary_and_episode_stay_readable_after_validated_archive_move(tmp_path,monkeypatch,metadata):
    import evolving_profile_controller_mcp as mcp
    if metadata:
        root,path,source,row=accepted_with_missing_metadata(tmp_path)
        p=ContextIncremental(tmp_path/'state',root,bank_id='bank-a');write_context_index(p.index,[row],[])
    else:p,path,row=accepted(tmp_path,monkeypatch)
    monkeypatch.setattr(mcp,'CONTEXT_INDEX_PATH',p.index)
    monkeypatch.setattr(mcp,'THREAD_SESSION_ROOT',path.parent)
    monkeypatch.setattr(mcp,'runtime_disabled',lambda *_:None)
    def forbidden(*_):raise AssertionError('Archive readback cannot invoke provider')
    p.discover(now=100);assert p.run_once({},now=200,processor=forbidden)['status']=='complete'
    archive=path.parent.parent/'archived_sessions';archive.mkdir();moved=archive/path.name;path.rename(moved)
    p.discover(now=300);assert p.run_once({},now=400,processor=forbidden)['status']=='complete'
    args={'scenario_type':'session','session_id':row['session_id'],'tier':'compact'}
    reply=json.loads(mcp.read_context_summary(args)['content'][0]['text'])
    assert reply['status']==('episode_directory_ready' if metadata else 'ready')
    assert reply['items'][0]['summary']==row['summary']['compact']
    assert reply['items'][0]['raw_source_files']==[str(moved)]
    eid=row['automated_source_coverage']['reviewed_episode_ids'][0]
    episode=json.loads(mcp.read_context_summary({**args,'episode_id':eid})['content'][0]['text'])
    assert episode['status']=='current'
    assert episode['items'][0]['raw_source_files']==[str(moved)]
    assert episode['items'][0]['summary']==(row['episodes'][0]['summary']['compact'] if metadata else row['summary']['compact'])
