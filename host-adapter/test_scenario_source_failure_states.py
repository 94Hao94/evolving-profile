"""No summary, unavailable raw format, and incomplete scan are different axes."""
import json
import pytest

SID='00000000-0000-4000-8000-000000000072'

def setup(tmp_path,monkeypatch):
    import evolving_profile_controller_mcp as mcp
    root=tmp_path/'sessions';root.mkdir()
    index=tmp_path/'index.json'
    index.write_text(json.dumps({'schema':'evolving-profile.context-index.v1','sessions':[],'projects':[]}))
    monkeypatch.setattr(mcp,'CONTEXT_INDEX_PATH',index)
    monkeypatch.setattr(mcp,'THREAD_SESSION_ROOT',root)
    monkeypatch.setattr(mcp.Path,'home',lambda:tmp_path)
    monkeypatch.setattr(mcp,'runtime_disabled',lambda *_:None)
    return mcp,root

def read(mcp):
    result=mcp.read_context_summary({'scenario_type':'session','scenario_id':f'session:{SID}/turn/requested','tier':'compact'})
    return json.loads(result['content'][0]['text'])

def test_compressed_original_is_not_misreported_as_a_missing_turn(tmp_path,monkeypatch):
    mcp,root=setup(tmp_path,monkeypatch)
    (root/f'rollout-test-{SID}.jsonl.zst').write_bytes(b'unknown compressed bytes')
    result=read(mcp)
    import shutil
    expected='source_decode_failed' if shutil.which('zstd') else 'source_compressed_unavailable'
    assert result['status']==expected
    assert result['summary_status']=='not_found'
    assert result['raw_source_status']==expected
    assert result['raw_source_read_attempted'] is True
    assert result['raw_source_coverage']['partial'] is True
    assert result['raw_source_coverage']['source_identity']=='unknown'
    assert result['items']==[]

@pytest.mark.parametrize('status',['source_scan_incomplete','source_comparison_incomplete','source_ambiguous','source_identity_mismatch','source_changed'])
def test_raw_unknown_status_and_coverage_survive_the_public_wrapper(tmp_path,monkeypatch,status):
    from lib import raw_session_evidence
    mcp,_=setup(tmp_path,monkeypatch)
    monkeypatch.setattr(raw_session_evidence,'read_evidence',lambda *_args,**_kwargs:{'status':status,'source':{},
        'coverage':{'partial':True,'scan_complete':False,'matched_messages':None}})
    result=read(mcp)
    assert result['status']==status and result['summary_status']=='not_found'
    assert result['raw_source_status']==status
    assert result['raw_source_coverage']=={'partial':True,'scan_complete':False,'matched_messages':None}
    assert result['items']==[]

def test_actually_missing_source_still_distinguishes_absent_summary_and_source(tmp_path,monkeypatch):
    mcp,_=setup(tmp_path,monkeypatch)
    result=read(mcp)
    assert result['status']=='not_found'
    assert result['summary_status']=='not_found'
    assert result['raw_source_status']=='source_missing'
    assert result['raw_source_coverage']['matched_messages'] is None

@pytest.mark.parametrize('source_status',['source_compressed_unavailable','source_comparison_incomplete'])
def test_background_unreadable_format_is_waiting_not_extraction_failed(tmp_path,source_status):
    from lib.context_incremental import ContextIncremental
    from test_context_incremental import rollout
    root=tmp_path/'sessions';rollout(root,SID)
    worker=ContextIncremental(tmp_path/'state',root,debounce=0)
    worker.discover(now=100)
    job=worker.claim(now=101)
    result=worker.fail(job,'scenario_'+source_status,now=102,terminal=True,
        qualification={'status':'waiting_source','reason':'scenario_'+source_status})
    assert result=='waiting_source'
    with worker.db() as db:assert db.execute('SELECT attempts FROM jobs').fetchone()[0]==1
