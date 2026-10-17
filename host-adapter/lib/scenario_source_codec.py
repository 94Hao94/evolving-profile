"""Bounded native source decoding. Logical offsets never seek compressed bytes.

A stream lives across leases in one worker. After interruption it replays the
verified prefix, charging all physical and decoded bytes again. It never writes
to the source or executes transcript content.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import select
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from .session_paths import session_roots
from .scenario_coverage_contract import contract

_BATCH_KEY=os.urandom(32)


def _batch_bytes(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),
        default=lambda v: {'raw_bytes_hex':v.hex()} if isinstance(v,bytes) else None).encode()


class VerifiedSourceBatch(dict):
    """In-process provenance capability; JSON/model dictionaries cannot replace it."""
    def __init__(self,value,location):
        super().__init__(value)
        self.location=dict(location)
        self.seal=hmac.digest(_BATCH_KEY,_batch_bytes([value,self.location]),'sha256')


class UnsupportedMessageSchema(ValueError):pass


def verify_source_batch(batch,location):
    return (isinstance(batch,VerifiedSourceBatch) and batch.location==location
        and hmac.compare_digest(batch.seal,hmac.digest(_BATCH_KEY,_batch_bytes([dict(batch),location]),'sha256')))


def physical_revision(path):
    stat=Path(path).stat()
    return [stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]


def locate_source(session_id, root):
    sid=str(uuid.UUID(str(session_id)))
    roots=session_roots(root)
    paths=[]
    for base in roots:
        if base.is_dir():
            for pattern in (f'rollout-*-{sid}.jsonl',f'rollout-*-{sid}.jsonl.zst'):
                paths.extend(base.rglob(pattern))
    if not paths:return {'status':'source_missing','session_id':sid}
    for path in paths:
        if path.is_symlink() or not any(path.resolve().is_relative_to(r.resolve()) for r in roots):
            return {'status':'source_path_rejected','session_id':sid}
        # Refuse symlinked intermediate directories as well.
        if any(p.is_symlink() for p in [path,*path.parents]):
            return {'status':'source_path_rejected','session_id':sid}
    if len(paths)!=1:return {'status':'source_ambiguous','session_id':sid}
    path=paths[0]
    return {'status':'ready','session_id':sid,'path':str(path),
            'root':str(next(r.resolve() for r in roots if path.resolve().is_relative_to(r.resolve()))),
            'codec':'zstd_jsonl' if path.suffix=='.zst' else 'plain_jsonl',
            'physical_revision':physical_revision(path)}


def decode_record(raw, sequence, offset, turn_id, session_id):
    """Decode one complete raw record; selection is explicit, never guessed."""
    row=json.loads(raw)
    if not isinstance(row,dict):raise ValueError('invalid_record_shape')
    kind=row.get('type');payload=row.get('payload')
    if kind in {'session_meta','turn_context','response_item'} and not isinstance(payload,dict):
        raise ValueError('invalid_record_payload')
    if sequence==0 and (kind!='session_meta' or payload.get('id')!=session_id):
        raise ValueError('source_identity_mismatch')
    if kind=='session_meta' and payload.get('id')!=session_id:raise ValueError('source_identity_mismatch')
    if kind=='turn_context':
        turn_id=payload.get('turn_id')
        if not isinstance(turn_id,str) or not turn_id:raise ValueError('invalid_turn_id')
    role=None;text='';selection='not_visible_message'
    if kind=='response_item' and payload.get('type')=='message':
        candidate_role=payload.get('role')
        phase,channel=payload.get('phase'),payload.get('channel')
        if not isinstance(candidate_role,str) or (phase is not None and not isinstance(phase,str)) or (channel is not None and not isinstance(channel,str)):
            raise ValueError('invalid_record_payload')
        if candidate_role=='assistant' and (
                phase not in {None,'final','final_answer','commentary','analysis'}
                or channel not in {None,'final','commentary','analysis'} or (phase is None and channel is None)):
            raise UnsupportedMessageSchema('unsupported_message_schema')
        final=(phase in {'final','final_answer'} and channel in {None,'final'}) or (channel=='final' and phase is None)
        if candidate_role=='user' or (candidate_role=='assistant' and final):
            role=candidate_role;content=payload.get('content')
            if not isinstance(content,list):raise ValueError('invalid_message_content')
            pieces=[]
            for part in content:
                if not isinstance(part,dict):raise ValueError('invalid_message_content')
                if part.get('type') in {'input_text','output_text','text'} or 'text' in part:
                    if not isinstance(part.get('text'),str):raise ValueError('invalid_message_content')
                    pieces.append(part['text'])
            text='\n'.join(pieces)
            selection='visible_message'
    sha=hashlib.sha256(raw).hexdigest()
    return {'unit_id':f'{sequence}:{sha}','sequence':sequence,'byte_offset':offset,
            'byte_length':len(raw),'offset_space':'decompressed_jsonl','raw_line_sha256':sha,
            'role':role,'turn_id':turn_id,'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'selection':selection,'_raw_line':raw},turn_id


class SourceStream:
    def __init__(self,location,checkpoint=None,*,permission,max_line_bytes=None,decoder=None):
        ceiling=contract()['defaults']['line_bytes']
        max_line_bytes=ceiling if max_line_bytes is None else max_line_bytes
        self.location=dict(location);self.permission=permission;self.max_line_bytes=max_line_bytes
        if type(max_line_bytes) is not int or not 1<=max_line_bytes<=ceiling:raise ValueError('line_limit_invalid')
        self.file=None;self.process=None;self.error=None;self.buffer=bytearray();self.pending=b''
        self.offset=0;self.sequence=0;self.turn_id=None;self.digest=hashlib.sha256();self.eof=False
        self.input_eof=False;self.replayed_bytes=0
        self.target=checkpoint or {};self.replay_done=not self.target.get('logical_offset',0)
        if location.get('status')!='ready':self.error=('unavailable',location.get('status'));return
        if self.target and self.target.get('physical_revision')!=location['physical_revision']:
            self.error=('invalid','source_changed');return
        if not permission():self.error=('unavailable','permission_denied');return
        path=Path(location['path'])
        if path.is_symlink() or physical_revision(path)!=location['physical_revision']:
            self.error=('invalid','source_changed');return
        self.file=os.fdopen(os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)),'rb',buffering=0)
        if location['codec']=='zstd_jsonl':
            executable=decoder or shutil.which('zstd')
            try:
                if not executable:raise FileNotFoundError()
                self.process=subprocess.Popen([executable,'-d','-q','-c'],stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
                os.set_blocking(self.process.stdin.fileno(),False)
                os.set_blocking(self.process.stdout.fileno(),False)
            except OSError:self.error=('unavailable','decoder_unavailable')

    def close(self):
        if self.process:
            if self.process.poll() is None:self.process.kill()
            self.process.wait(timeout=5)
            for pipe in (self.process.stdin,self.process.stdout):
                if pipe and not pipe.closed:pipe.close()
        if self.file:self.file.close()

    def __enter__(self):return self
    def __exit__(self,*_):self.close()

    def checkpoint(self):
        return {'physical_revision':self.location.get('physical_revision'),
                'logical_offset':self.offset,'next_sequence':self.sequence,'turn_id':self.turn_id,
                'prefix_sha256':self.digest.hexdigest(),'offset_space':'decompressed_jsonl'}


def open_source_stream(location,checkpoint=None,**kwargs):
    return SourceStream(location,checkpoint,**kwargs)


def read_source_batch(stream,checkpoint=None,limits=None):
    if checkpoint and checkpoint!=stream.checkpoint():raise ValueError('checkpoint_does_not_match_stream')
    limits=limits or {}
    defaults=contract()['defaults']
    output_limit=limits.get('output_bytes',defaults['output_bytes']);input_limit=limits.get('input_bytes',defaults['input_bytes'])
    seconds=limits.get('wall_seconds',defaults['wall_seconds'])
    if (type(output_limit) is not int or not 1<=output_limit<=defaults['output_bytes']
            or type(input_limit) is not int or not 1<=input_limit<=defaults['input_bytes']
            or type(seconds) not in (int,float) or not 0<seconds<=defaults['wall_seconds']):raise ValueError('source_limits_invalid')
    started=time.monotonic();read=0;fed=0;units=[];reason='lease_limit';status='partial'
    if not stream.error:
        try:
            if not stream.permission():stream.error=('unavailable','permission_denied')
            elif physical_revision(stream.location['path'])!=stream.location['physical_revision']:
                stream.error=('invalid','source_changed')
        except OSError:stream.error=('invalid','source_changed')
    while not stream.error:
        while b'\n' in stream.buffer:
            pos=stream.buffer.index(10)+1
            if pos>stream.max_line_bytes:stream.error=('partial','line_limit');break
            raw=bytes(stream.buffer[:pos])
            try:unit,turn=decode_record(raw,stream.sequence,stream.offset,stream.turn_id,stream.location['session_id'])
            except UnsupportedMessageSchema:
                stream.error=('partial','unsupported_message_schema');break
            except (ValueError,UnicodeError,RecursionError) as error:
                stream.error=('invalid',str(error) if str(error) in {'source_identity_mismatch','invalid_record_shape','invalid_record_payload','invalid_turn_id','invalid_message_content'} else 'invalid_json');break
            del stream.buffer[:pos];stream.digest.update(raw);stream.offset+=len(raw);stream.sequence+=1;stream.turn_id=turn
            if not stream.replay_done:
                stream.replayed_bytes+=len(raw)
                if stream.offset>stream.target['logical_offset']:stream.error=('invalid','checkpoint_not_record_boundary');break
                if stream.offset==stream.target['logical_offset']:
                    if (stream.digest.hexdigest()!=stream.target.get('prefix_sha256') or stream.sequence!=stream.target.get('next_sequence')
                            or stream.turn_id!=stream.target.get('turn_id')):stream.error=('invalid','checkpoint_prefix_changed');break
                    stream.replay_done=True
            else:units.append(unit)
        if stream.error:break
        if len(stream.buffer)>=stream.max_line_bytes:stream.error=('partial','line_limit');break
        if stream.eof:
            if stream.buffer:stream.error=('partial','incomplete_record');break
            if not stream.replay_done:stream.error=('invalid','checkpoint_beyond_source');break
            status='complete';reason=None;break
        if time.monotonic()-started>=seconds:reason='wall_limit';break
        if read>=output_limit:reason='output_limit';break
        capacity=min(65536,output_limit-read,stream.max_line_bytes-len(stream.buffer))
        if not stream.process:
            capacity=min(capacity,input_limit-fed)
            if capacity<=0:reason='input_limit';break
            data=stream.file.read(capacity);fed+=len(data)
        else:
            proc=stream.process
            # Both pipes are bounded, nonblocking. Keep decoder alive across leases.
            if not stream.input_eof and not stream.pending and fed<input_limit:
                stream.pending=stream.file.read(min(65536,input_limit-fed))
                if not stream.pending:
                    stream.input_eof=True;proc.stdin.close()
            writes=[proc.stdin] if stream.pending and not proc.stdin.closed and fed<input_limit else []
            readable,writable,_=select.select([proc.stdout],writes,[],min(.02,max(0,seconds-(time.monotonic()-started))))
            if writable:
                try:n=os.write(proc.stdin.fileno(),stream.pending[:input_limit-fed])
                except BrokenPipeError:n=0;stream.error=('invalid','decoder_failed')
                stream.pending=stream.pending[n:];fed+=n
            data=b''
            if readable:
                try:data=os.read(proc.stdout.fileno(),capacity)
                except BlockingIOError:continue
                if not data:
                    code=proc.poll()
                    if code is None:continue
                    if code!=0:stream.error=('invalid','decoder_failed');break
                    stream.eof=True
            elif fed>=input_limit and not readable:reason='input_limit';break
        if data:stream.buffer.extend(data);read+=len(data)
        elif not stream.process:stream.eof=True
    if stream.error:status,reason=stream.error
    # Units preceding an error are still only partial structure, never semantics.
    return VerifiedSourceBatch({'status':status,'reason':reason,'units':units,'checkpoint':stream.checkpoint(),
            'read_bytes':read,'input_bytes':fed,'replayed_bytes':stream.replayed_bytes,
            'partial':status!='complete','semantic_review_status':'not_reviewed',
            'source_identity_verified':stream.sequence>0,'codec':stream.location.get('codec')},stream.location)
