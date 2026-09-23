"""Bounded observation of native cross-task delivery. Never manufactures user input."""
import hashlib
import json
from pathlib import Path
import re
import uuid
from memory_turn_check import register

ENVELOPE=re.compile(r'\A<codex_delegation>\s*<source_thread_id>([^<]+)</source_thread_id>\s*<input>([\s\S]*)</input>\s*</codex_delegation>\s*\Z')

def observe(hook,root=None,byte_limit=524288):
    result={'status':'unavailable','check_ids':[],'bytes_read':0,'errors':[]}
    session,turn,path=hook.get('session_id'),hook.get('turn_id'),hook.get('transcript_path')
    if not all(isinstance(v,str) and v for v in (session,turn,path)):return result
    if type(byte_limit) is not int or not 1<=byte_limit<=2097152:raise ValueError('invalid scan budget')
    try:
        with Path(path).open('rb') as f:
            header=f.readline(65537);result['bytes_read']+=len(header)
            if len(header)>65536:result['status']='header_too_large';return result
            meta=json.loads(header)
            if meta.get('type')!='session_meta' or meta.get('payload',{}).get('id')!=session:
                result['status']='session_mismatch';return result
            header_end=f.tell();f.seek(0,2);size=f.tell();start=max(header_end,size-byte_limit)
            bounded=start>header_end;f.seek(start)
            tail=f.read(byte_limit);result['bytes_read']+=len(tail)
        if bounded:
            # A cut JSON record cannot provide a trustworthy namespace or turn.
            tail=tail.split(b'\n',1)[1] if b'\n' in tail else b''
        lines=tail.splitlines(keepends=True)
        for line in lines:
            if not line.endswith(b'\n'):
                result['errors'].append('partial_trailing_record');continue
            try:
                row=json.loads(line);p=row.get('payload',{})
                if row.get('type')!='response_item' or p.get('type')!='function_call_output':continue
                if p.get('namespace')!='codex_app' or p.get('name')!='send_message_to_thread':continue
                if (p.get('internal_chat_message_metadata_passthrough') or {}).get('turn_id')!=turn:continue
                mid=p.get('id');output=p.get('output')
                if not isinstance(mid,str) or not mid or not isinstance(output,str):continue
                match=ENVELOPE.fullmatch(output)
                if not match:result['errors'].append('malformed_native_delegation');continue
                source=str(uuid.UUID(match[1]));raw=match[2]
                cid='delegated_'+hashlib.sha256((session+'|'+mid).encode()).hexdigest()[:32]
                register({'invocation_id':cid,'session_id':session,'turn_id':turn,'raw_prompt':raw,'at':row.get('timestamp'),
                    'execution_mode':'native_delegation','prompt_origin':'agent_delegation','default_profile_source_ids':[],
                    'entry_kind':'native_delegation','source_session_id':source,'native_item_id':mid,
                    'native_output_sha256':hashlib.sha256(output.encode()).hexdigest(),
                    'registration_stage':'native_hook_observation','source_uri':str(path)},root)
                result['check_ids'].append(cid)
            except (ValueError,TypeError,KeyError) as error:result['errors'].append(type(error).__name__)
        result['check_ids']=list(dict.fromkeys(result['check_ids']))
        result['status']=('matched_bounded_window' if result['check_ids'] else 'no_match_bounded_window') if bounded else ('matched' if result['check_ids'] else 'no_match')
    except (OSError,ValueError,TypeError) as error:result['errors'].append(type(error).__name__)
    return result
