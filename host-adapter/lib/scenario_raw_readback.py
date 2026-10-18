"""Bounded compressed source readback, optionally from verified raw materialization.

Materialized records are original decoded JSONL bytes, never cached summaries.
They are checked against immutable unit hash/role and the current physical
source version before and after reading. No Provider or external facts involved.
"""
import hashlib
import json
from pathlib import Path

from .content import extract_user_request,is_synthetic_codex_user_message
from .scenario_source_codec import locate_source,open_source_stream,read_source_batch,decode_record
from .scenario_coverage_store import CoverageStore
from .scenario_coverage_contract import contract
from .scenario_coverage_contract import fingerprint


def read_materialized_page(snapshot,*,unit_id,text_offset,max_chars,permission,coverage_root):
    """One exact raw-message page; no summary fallback, no external truth claim."""
    if (type(text_offset) is not int or text_offset<0 or type(max_chars) is not int
            or not 1<=max_chars<=12000):raise ValueError('source_page_bounds_invalid')
    store=CoverageStore(Path(coverage_root)/'coverage.sqlite3',readonly=True)
    if not store.validate_snapshot(snapshot['snapshot_id'],permission)['valid']:raise ValueError('source_page_stale_or_forbidden')
    actual_snapshot=store.read(snapshot['snapshot_id'])
    if actual_snapshot['scope']!=snapshot['scope'] or actual_snapshot['generation']!=snapshot['generation']:raise ValueError('source_page_scope_changed')
    unit=next((u for u in actual_snapshot['units'] if u['unit_id']==unit_id and u['selection']=='visible_message'),None)
    if unit is None:raise ValueError('source_page_unit_unknown')
    location=locate_source(snapshot['location']['session_id'],snapshot['location']['root'])
    if location!=snapshot['location']:raise ValueError('source_page_location_changed')
    with store.connect() as db:
        size=db.execute('SELECT length(raw) FROM raw_units WHERE snapshot_id=? AND sequence=?',
            (snapshot['snapshot_id'],unit['sequence'])).fetchone()
        if size is None or size[0]>contract()['defaults']['line_bytes']:raise ValueError('source_page_materialization_unavailable')
        row=db.execute('SELECT raw FROM raw_units WHERE snapshot_id=? AND sequence=?',(snapshot['snapshot_id'],unit['sequence'])).fetchone()
    decoded,_=decode_record(row[0],unit['sequence'],unit['byte_offset'],unit['turn_id'],location['session_id'])
    if {k:v for k,v in decoded.items() if k!='_raw_line'}!=unit:raise ValueError('source_page_raw_changed')
    text=decoded['text']
    if text_offset>len(text):raise ValueError('source_page_bounds_invalid')
    end=min(len(text),text_offset+max_chars)
    if not store.validate_snapshot(snapshot['snapshot_id'],permission)['valid']:raise ValueError('source_page_stale_or_forbidden')
    return {'page_id':fingerprint([snapshot['snapshot_id'],unit_id,text_offset,end]),'unit_id':unit_id,
        'text':text[text_offset:end],'text_offset':text_offset,'text_total_chars':len(text),
        'next_offset':end if end<len(text) else None,'role':unit['role'],'turn_id':unit['turn_id'],
        'raw_line_sha256':unit['raw_line_sha256'],'source_readback':end>text_offset,
        'source_type':'codex_thread_history','external_fact_verified':False}


def _response(session_id,turn_id,units,*,complete,reason,read_bytes,max_chars,method):
    pieces=[];locators=[];used=0;clipped=False;matched=0
    for unit,raw,path in units:
        if unit['selection']!='visible_message' or (turn_id is not None and unit['turn_id']!=turn_id):continue
        text=unit['text']
        if unit['role']=='user':
            if is_synthetic_codex_user_message(text):continue
            text=extract_user_request(text)
        if not text:continue
        matched+=1
        if used>=max_chars:clipped=True;continue
        at=json.loads(raw).get('timestamp')
        full=f"[role: {unit['role']}; turn: {unit['turn_id']}; at: {at}]\n{text}"
        excerpt=full[:max_chars-used];used+=len(excerpt);pieces.append(excerpt);clipped|=len(excerpt)<len(full)
        locators.append({'source_path':path,'byte_offset':unit['byte_offset'],'offset_space':'decompressed_jsonl',
            'raw_line_sha256':unit['raw_line_sha256'],'role':unit['role'],'turn_id':unit['turn_id'],'at':at})
    return {'source_type':'codex_thread_history','claims_independently_verified':False,
        'boundary':'original_message_readback_not_artifact_or_external_fact_verification',
        'status':'source_read' if pieces else ('source_empty' if complete else 'source_scan_incomplete'),
        'source':{'text':'\n\n'.join(pieces),'locators':locators,'session_id':session_id,'turn_id':turn_id,
            'verbatim_message_excerpts':True,'read_method':method},
        'coverage':{'matched_messages':matched if complete else None,'returned_messages':len(locators),
            'partial':not complete or clipped,'scan_complete':complete,'scanned_bytes':read_bytes,'scan_stop_reason':reason}}


def read_materialized(session_id,root,coverage_root,*,turn_id,max_chars,max_line_bytes,raw_line_sha256=None):
    coverage_root=Path(coverage_root)
    if not (coverage_root/'coverage.sqlite3').is_file():return None
    try:
        with (coverage_root/'status'/f'{session_id}.json').open('rb') as f:raw=f.read(1024*1024+1)
        if len(raw)>1024*1024:return None
        status=json.loads(raw);store=CoverageStore(coverage_root/'coverage.sqlite3',readonly=True)
        snapshot=store.read(status['snapshot_id']);loc=locate_source(session_id,root)
        if (loc!=snapshot['location'] or snapshot['selection_version']!=contract()['source_selection_version']
                or not snapshot['source_manifest_complete']):return None
        if not store.validate_snapshot(snapshot['snapshot_id'],snapshot['permission'])['valid']:return None
        wanted={u['sequence']:u for u in snapshot['units'] if u['selection']=='visible_message'
            and (turn_id is None or u['turn_id']==turn_id) and (raw_line_sha256 is None or u['raw_line_sha256']==raw_line_sha256)}
        units=[];read=0;limit_hit=False
        with store.connect() as db:
            for seq,expected in wanted.items():
                size=db.execute('SELECT length(raw) FROM raw_units WHERE snapshot_id=? AND sequence=?',(snapshot['snapshot_id'],seq)).fetchone()
                if size is None:return None
                if size[0]>max_line_bytes or read+size[0]>16*1024*1024:limit_hit=True;break
                record=db.execute('SELECT raw FROM raw_units WHERE snapshot_id=? AND sequence=?',(snapshot['snapshot_id'],seq)).fetchone()[0]
                actual,_=decode_record(record,seq,expected['byte_offset'],expected['turn_id'],session_id)
                if {k:v for k,v in actual.items() if k!='_raw_line'}!=expected:return None
                units.append((actual,record,loc['path']));read+=len(record)
        if not store.validate_snapshot(snapshot['snapshot_id'],snapshot['permission'])['valid']:return None
        return _response(session_id,turn_id,units,complete=not limit_hit,reason='materialization_read_limit' if limit_hit else None,
            read_bytes=read,max_chars=max_chars,method='verified_decoded_raw_records')
    except (OSError,ValueError,KeyError,TypeError):return None


def read_compressed(session_id,root,*,turn_id,max_chars,max_scan_bytes,max_line_bytes,coverage_root=None,raw_line_sha256=None):
    if coverage_root:
        materialized=read_materialized(session_id,root,coverage_root,turn_id=turn_id,max_chars=max_chars,max_line_bytes=max_line_bytes,raw_line_sha256=raw_line_sha256)
        if materialized is not None:return materialized
    location=locate_source(session_id,root)
    if location.get('status')!='ready':return None
    defaults=contract()['defaults']
    with open_source_stream(location,permission=lambda:True,max_line_bytes=min(max_line_bytes,defaults['line_bytes'])) as stream:
        batch=read_source_batch(stream,limits={'input_bytes':min(max_scan_bytes,defaults['input_bytes']),
            'output_bytes':min(max_scan_bytes,defaults['output_bytes']),'wall_seconds':defaults['wall_seconds']})
    if batch['status'] in {'invalid','unavailable'}:
        return {'source_type':'codex_thread_history','claims_independently_verified':False,
            'status':'source_compressed_unavailable' if batch['reason']=='decoder_unavailable' else 'source_decode_failed',
            'source':{},'coverage':{'partial':True,'scan_complete':False,'matched_messages':None,
                'source_presence':'compressed_file_present_unverified','source_identity':'unknown','reason':batch['reason']}}
    return _response(session_id,turn_id,[(u,u['_raw_line'],location['path']) for u in batch['units'] if raw_line_sha256 is None or u['raw_line_sha256']==raw_line_sha256],
        complete=batch['status']=='complete',reason=batch['reason'],read_bytes=batch['read_bytes'],max_chars=max_chars,
        method='bounded_zstd_decode' if location['codec']=='zstd_jsonl' else 'bounded_plain_decode')
