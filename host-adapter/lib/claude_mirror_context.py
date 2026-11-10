"""Read-only exact legacy-mirror proof; ambiguous sources retain all messages."""
import hashlib
import json
import os
import re
import stat
import uuid
from datetime import datetime,timezone
from pathlib import Path

DEFAULT_HOME=Path.home()
LEGACY_SHA256='a680ed6fb94b4369992226cd6359eb309c95c859aba38c4e141aa82675dc0e0d'
SKIP=('<system-reminder>','<command-','<local-command','<ep_','<evolving_profile','<scheduled-task','[SCHEDULED TASK - AUTOMATED FIRING')

def _safe(path):
    return not any(p.is_symlink() for p in (path,*path.parents))

def _stamp(path):
    s=path.stat()
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def _read(path,limit):
    if not _safe(path):raise ValueError('unsafe_path')
    before=_stamp(path)
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(fd,'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('nonregular_source')
        raw=stream.read(limit+1)
    if len(raw)>limit or before!=_stamp(path):raise ValueError('source_drift_or_budget')
    return raw,before

def _text(value):
    if isinstance(value,str):return value.strip()
    if isinstance(value,list):return '\n'.join(v for v in map(_text,value) if v).strip()
    if isinstance(value,dict):
        if value.get('type') in ('tool_use','tool_result','thinking','redacted_thinking','image'):return ''
        if 'text' in value:return str(value.get('text') or '').strip()
        if 'content' in value:return _text(value['content'])
    return ''

def _iso(ts,fallback):
    try:
        if isinstance(ts,(int,float)):return datetime.fromtimestamp(ts/(1000 if ts>1e12 else 1),tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]+'Z'
        if isinstance(ts,str) and ts:return datetime.fromisoformat(ts.replace('Z','+00:00')).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]+'Z'
    except (ValueError,OverflowError,OSError):pass
    return fallback

def _encode(row):return (json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n').encode()

def _resolve_native(home,sid):
    paths=list((home/'.claude/projects').glob('*/'+sid+'.jsonl'))
    for app in ('Claude','Claude-3p'):
        root=home/'Library/Application Support'/app/'local-agent-mode-sessions'
        paths.extend(root.glob('*/*/*/.claude/projects/*/'+sid+'.jsonl'))
    # Even identical duplicate copies are ambiguous native authority.
    if len(paths)!=1 or not _safe(paths[0]):raise ValueError('native_missing_or_ambiguous')
    return paths[0]

def proof_is_current(proof):
    try:return all(_safe(Path(path)) and _stamp(Path(path))==stamp for path,stamp in proof['snapshots'])
    except (OSError,KeyError,TypeError,ValueError):return False

def machine_context_proof(mirror,session_id,*,home=None):
    """One bounded read/reconstruction per mirror; never imports native code.

    The checked legacy implementation is reproduced below as a pure projection.
    Every reconstructed byte must match. No historical timestamp inference,
    text-only alignment, registry, source rewrite or fallback authority exists.
    """
    try:
        home=Path(home or DEFAULT_HOME);mirror=Path(mirror);sid=str(uuid.UUID(str(session_id)))
        if not home.is_absolute() or not mirror.is_absolute() or '..' in home.parts or '..' in mirror.parts:return None
        base=home/'.evolving-profile/claude-code';root=base/'rollouts'
        if not mirror.is_relative_to(root) or not _safe(mirror) or not mirror.resolve().is_relative_to(root.resolve()):return None
        code=base/'desktop_rollout.py';code_raw,code_stamp=_read(code,128*1024)
        if hashlib.sha256(code_raw).hexdigest()!=LEGACY_SHA256:return None
        native=_resolve_native(home,sid)
        raw,native_stamp=_read(native,128*1024*1024);mirror_raw,mirror_stamp=_read(mirror,16*1024*1024)
        first=json.loads(mirror_raw.splitlines()[0]);head=first.get('payload') or {}
        if first.get('type')!='session_meta' or head.get('id')!=sid or head.get('cli_version')!='desktop-bridge-1':return None
        fallback=_iso(native_stamp[3]/1e9,'1970-01-01T00:00:00.000Z')
        messages=[];machine=[];human=set();offset=0
        for line in raw.splitlines(keepends=True):
            at=offset;offset+=len(line)
            if len(line)>8*1024*1024:return None
            try:entry=json.loads(line.decode('utf-8',errors='replace'))
            except (ValueError,TypeError):continue
            if not isinstance(entry,dict):return None
            if entry.get('sessionId') not in (None,sid):return None
            msg=entry.get('message') if isinstance(entry.get('message'),dict) else None
            role=entry.get('role') or (msg or {}).get('role') or entry.get('type')
            text=_text((msg or {}).get('content') if msg is not None else entry.get('content'))
            witness={'source_path':str(native),'byte_offset':at,'raw_line_sha256':hashlib.sha256(line).hexdigest(),'record_type':entry.get('type')}
            if role=='user' and entry.get('type')=='user' and entry.get('sessionId')==sid and entry.get('isMeta') is True and entry.get('turnCompanion') is True and text:machine.append((text,witness))
            if role=='user' and entry.get('type')!='api-request-blob' and not entry.get('isMeta') and not entry.get('isSidechain') and text:human.add(text)
            attached=entry.get('attachment')
            if (entry.get('type')=='attachment' and isinstance(attached,dict) and attached.get('type')=='queued_command'
                    and (attached.get('origin') or {}).get('kind')=='human' and attached.get('humanTurn') is True
                    and isinstance(attached.get('prompt'),str)):human.add(attached['prompt'].strip())
            if role not in ('user','assistant') or entry.get('isSidechain') or entry.get('isMeta') or not text or text.startswith(SKIP):continue
            if role=='user' and ((text.startswith('<ta<API_KEY>>') and '<task-id>' in text and '<status>' in text and '</ta<API_KEY>>' in text)
                    or (text.startswith('Another Claude session sent a message:') and '<agent-message ' in text and '[Subagent hand-back]' in text)):role='assistant'
            api=(set(entry)=={'type','sessionId','hash','message'} and entry.get('type')=='api-request-blob'
                and isinstance((msg or {}).get('content'),(str,list))
                and isinstance(entry.get('hash'),str) and bool(re.fullmatch('[0-9a-f]{64}',entry['hash'])))
            messages.append({'role':role,'text':text,'at':_iso(entry.get('timestamp'),fallback),'api':api,'witness':witness})
        while messages and messages[0]['role']!='user':messages.pop(0)
        if not messages or not any(m['role']=='assistant' for m in messages):return None
        timestamp=messages[0]['at'];host=head.get('source') or 'claude-desktop';cwd=head.get('cwd') or ''
        rows=[({'timestamp':timestamp,'type':'session_meta','payload':{'id':sid,'timestamp':timestamp,'cwd':cwd,'originator':host,'source':host,'cli_version':'desktop-bridge-1'}},None)]
        turns=[];current=None
        for message in messages:
            if message['role']=='user':current={'user':message,'assistant':[]};turns.append(current)
            elif current is not None:current['assistant'].append(message)
        for n,turn in enumerate(turns,1):
            user=turn['user'];text=user['text'];text=text if len(text)<=400000 else text[:400000]+'\n[truncated by desktop_rollout]'
            tid=str(uuid.uuid5(uuid.UUID(sid),f'turn-{n}'))
            rows.append(({'timestamp':user['at'],'type':'turn_context','payload':{'turn_id':tid,'cwd':cwd}},None))
            rows.append(({'timestamp':user['at'],'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':text}]}},user))
            rows.append(({'timestamp':user['at'],'type':'event_msg','payload':{'type':'user_message','message':text}},None))
            for i,answer in enumerate(turn['assistant']):
                text=answer['text'];text=text if len(text)<=400000 else text[:400000]+'\n[truncated by desktop_rollout]'
                rows.append(({'timestamp':answer['at'],'type':'response_item','payload':{'type':'message','role':'assistant',
                    'phase':'final_answer' if i==len(turn['assistant'])-1 else 'commentary','content':[{'type':'output_text','text':text}]}},answer))
        encoded=[_encode(row) for row,_ in rows]
        if b''.join(encoded)!=mirror_raw:return None
        proof={'snapshots':[(str(code),code_stamp),(str(native),native_stamp),(str(mirror),mirror_stamp)],'exclusions':{}}
        offset=0
        for (row,message),line in zip(rows,encoded):
            if message and message['role']=='user' and message['api'] and len(message['text'])<=400000 and message['text'] not in human:
                antecedents=[w for t,w in machine if t==message['text'] and w['byte_offset']<message['witness']['byte_offset']]
                if antecedents:
                    proof['exclusions'][(offset,hashlib.sha256(line).hexdigest())]={
                        'metadata_kind':'native_api_replay_machine_companion','original_role':'user','fact_authority':'none',
                        'excluded_from_semantic_input':True,'native_source_path':str(native),'native_source_sha256':hashlib.sha256(raw).hexdigest(),
                        'mirror_source_sha256':hashlib.sha256(mirror_raw).hexdigest(),'legacy_code_sha256':LEGACY_SHA256,
                        'native_api_record':message['witness'],'machine_antecedents':antecedents}
            offset+=len(line)
        return proof if proof_is_current(proof) else None
    except (OSError,ValueError,KeyError,TypeError,AttributeError,IndexError,OverflowError):return None
