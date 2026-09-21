"""Independent read-only native user-message inventory, not a retention writer."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

def prompt_hash(text):
    return hashlib.sha256(' '.join(str(text).split()).encode()).hexdigest()

def scan(path,session_id,since):
    path=Path(path);result={'messages':[],'excluded_count':0,'complete':True,'errors':[],'bytes_read':0}
    try:
        with path.open('rb') as f:
            while True:
                offset=f.tell();line=f.readline()
                if not line:break
                result['bytes_read']+=len(line)
                if not line.endswith(b'\n'):
                    result['complete']=False;result['errors'].append({'offset':offset,'reason':'partial_trailing_line'});break
                head=line[:1000]
                if not re.search(rb'"type"\s*:\s*"response_item"',head) or not re.search(rb'"role"\s*:\s*"user"',head):continue
                at=re.search(rb'"timestamp"\s*:\s*"([^"]+)"',head)
                if not at or at[1].decode()<since:continue
                try:
                    obj=json.loads(line);p=obj['payload']
                    if p.get('type')!='message' or p.get('role')!='user':continue
                    text='\n'.join(i.get('text','') for i in p.get('content',[]) if isinstance(i,dict))
                    if text.strip().startswith('Hindsight系统一次性检查提示，不是用户新增需求：'):
                        from memory_turn_check import is_recorded_completion_prompt
                        if is_recorded_completion_prompt(text):
                            result['excluded_count']+=1;continue
                    if re.fullmatch(r'\s*<environment_context>.*</environment_context>\s*',text,re.S):
                        result['excluded_count']+=1;continue
                    mid=p.get('id');meta=p.get('internal_chat_message_metadata_passthrough') or {}
                    result['messages'].append({'occurrence_id':session_id+':'+str(mid or 'offset:'+str(offset)),
                        'message_id':mid,'session_id':session_id,'turn_id':meta.get('turn_id'),'at':obj['timestamp'],
                        'source_path':str(path),'byte_offset':offset,'prompt':text,'prompt_hash':prompt_hash(text),
                        'identity_basis':'native_message_id' if mid else 'native_file_offset'})
                except (ValueError,KeyError,TypeError) as e:
                    result['complete']=False;result['errors'].append({'offset':offset,'reason':type(e).__name__})
    except OSError as e:result['complete']=False;result['errors'].append({'reason':type(e).__name__})
    return result

def _seconds(at):
    try:return dt.datetime.fromisoformat(at.replace('Z','+00:00')).timestamp()
    except (ValueError,AttributeError):return None

def reconcile(messages,captures):
    options=[]
    for m in messages:
        candidates=[]
        for c in captures:
            if c.get('session_id')!=m.get('session_id'):continue
            exact=bool(m.get('message_id') and c.get('message_id')==m['message_id'])
            a,b=_seconds(m.get('at')),_seconds(c.get('at'))
            weak=c.get('prompt_hash')==m.get('prompt_hash') and a is not None and b is not None and abs(a-b)<=120
            if exact or weak:candidates.append((c['event_id'],'native_message_id' if exact else 'text_session_time_review_required'))
        options.append(candidates)
    uses={eid:sum(eid in [e for e,_ in matches] for matches in options) for matches in options for eid,_ in matches}
    result=[]
    for m,matches in zip(messages,options):
        state='missing' if not matches else 'matched' if len(matches)==1 and uses[matches[0][0]]==1 else 'ambiguous'
        result.append(dict(m,capture_state=state,capture_candidates=[e for e,_ in matches],
                           capture_join=matches[0][1] if state=='matched' else None))
    return result
