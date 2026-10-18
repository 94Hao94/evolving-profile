import hashlib
import json
import shutil
import subprocess

import pytest

from lib import scenario_source_codec as codec

SID = '00000000-0000-4000-8000-000000000078'


def source(tmp_path, compressed=False, text='不要删除原文件🙂，只作检查。'):
    root=tmp_path/'sessions'; root.mkdir(exist_ok=True)
    rows=[{'type':'session_meta','payload':{'id':SID}},
          {'type':'turn_context','payload':{'turn_id':'t1'}},
          {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':text}]}},
          {'type':'response_item','payload':{'type':'message','role':'assistant','channel':'final','content':[{'type':'output_text','text':'完成（助手自述）'}]}}]
    raw=b''.join((json.dumps(row,ensure_ascii=False)+'\n').encode() for row in rows)
    path=root/f'rollout-test-{SID}.jsonl'
    if compressed:
        if not shutil.which('zstd'):pytest.skip('optional zstd CLI not installed')
        path=path.with_suffix('.jsonl.zst')
        path.write_bytes(subprocess.run(['zstd','-q','-c'],input=raw,capture_output=True,check=True).stdout)
    else:path.write_bytes(raw)
    return root,path,raw


def collect(root, **kw):
    location=codec.locate_source(SID,root)
    with codec.open_source_stream(location,permission=lambda:True,**kw) as stream:
        batches=[]
        for _ in range(100):
            b=codec.read_source_batch(stream,limits={'output_bytes':256,'input_bytes':256,'wall_seconds':1})
            batches.append(b)
            if b['status']!='partial':break
    return batches


def test_plain_and_single_frame_zstd_have_identical_verified_units(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    plain,_,raw=source(a);zstd,_,_=source(b,True)
    pa=collect(plain);pb=collect(zstd)
    assert pa[-1]['status']==pb[-1]['status']=='complete'
    ua=[u for p in pa for u in p['units']];ub=[u for p in pb for u in p['units']]
    assert [(u['raw_line_sha256'],u['role'],u['turn_id'],u['text']) for u in ua]==[(u['raw_line_sha256'],u['role'],u['turn_id'],u['text']) for u in ub]
    assert len(ua)==4 and ua[2]['text']=='不要删除原文件🙂，只作检查。'
    assert pb[-1]['checkpoint']['logical_offset']==len(raw)
    assert pb[-1]['checkpoint']['prefix_sha256']==hashlib.sha256(raw).hexdigest()
    assert all(p['read_bytes']<=256 and p['input_bytes']<=256 for p in pb)
    assert all(u['offset_space']=='decompressed_jsonl' for u in ub)


def test_restart_replays_and_checks_prefix_instead_of_compressed_seek(tmp_path):
    root,_,_=source(tmp_path,True)
    location=codec.locate_source(SID,root)
    with codec.open_source_stream(location,permission=lambda:True) as stream:
        first=codec.read_source_batch(stream,limits={'output_bytes':256,'input_bytes':256,'wall_seconds':1})
    with codec.open_source_stream(location,checkpoint=first['checkpoint'],permission=lambda:True) as stream:
        later=[]
        for _ in range(30):
            p=codec.read_source_batch(stream,limits={'output_bytes':256,'input_bytes':256,'wall_seconds':1});later.append(p)
            if p['status']!='partial':break
    assert later[-1]['status']=='complete'
    assert later[-1]['replayed_bytes']>=first['checkpoint']['logical_offset']
    assert all(u['sequence']>=first['checkpoint']['next_sequence'] for p in later for u in p['units'])


def test_decoder_missing_and_corruption_are_not_source_missing(tmp_path):
    root,path,_=source(tmp_path,True)
    missing=collect(root,decoder='/not-installed/zstd')
    assert missing[-1]['reason']=='decoder_unavailable' and missing[-1]['status']=='unavailable'
    path.write_bytes(b'broken')
    bad=collect(root)
    assert bad[-1]['status']=='invalid' and bad[-1]['reason']=='decoder_failed'


def test_permission_and_source_changes_stop_existing_stream(tmp_path):
    root,path,_=source(tmp_path)
    allowed=[True]
    with codec.open_source_stream(codec.locate_source(SID,root),permission=lambda:allowed[0]) as stream:
        allowed[0]=False
        assert codec.read_source_batch(stream)['reason']=='permission_denied'
    with codec.open_source_stream(codec.locate_source(SID,root),permission=lambda:True) as stream:
        path.write_bytes(path.read_bytes()+b'{}\n')
        assert codec.read_source_batch(stream)['reason']=='source_changed'


def test_oversized_or_malformed_records_never_skip_to_later_text(tmp_path):
    root,_,_=source(tmp_path,text='x'*2000)
    batches=collect(root,max_line_bytes=300)
    assert batches[-1]['status']=='partial' and batches[-1]['reason']=='line_limit'
    assert not any(u['role']=='assistant' for p in batches for u in p['units'])


def test_symlink_outside_root_rejected(tmp_path):
    root=tmp_path/'sessions';root.mkdir()
    outside=tmp_path/'outside';outside.write_text('{}\n')
    (root/f'rollout-test-{SID}.jsonl').symlink_to(outside)
    assert codec.locate_source(SID,root)['status']=='source_path_rejected'


def test_unknown_assistant_phase_cannot_silently_become_complete_coverage(tmp_path):
    root,path,raw=source(tmp_path)
    rows=[json.loads(line) for line in raw.splitlines()]
    rows[-1]['payload'].pop('channel')
    rows[-1]['payload']['phase']='new_unknown_final_schema'
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    batch=collect(root)[-1]
    assert batch['status']=='partial' and batch['reason']=='unsupported_message_schema'
