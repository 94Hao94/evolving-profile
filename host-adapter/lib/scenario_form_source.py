"""Native asynchronous answers: exact raw witnesses, no question-to-user promotion."""
import hashlib
import json
import re
from pathlib import Path

TAG = 'send_user_message_question_reply'
MAX_LINE = 8 * 1024 * 1024

def question_context_fields(row):
    """Explicit context only; never becomes a user quote or independent request."""
    context=row.get('form_reply_context')
    if not isinstance(context,dict) or context.get('schema')!='evolving-profile.native-form-answer.v1':return {}
    from source_safety import mask_text
    return {'question_context':[mask_text(q) for q in context['questions']],
            'question_authority':'assistant_question_context_not_user_request'}

def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ValueError('duplicate_key')
        value[key] = item
    return value

def _json(value):
    return json.loads(value, object_pairs_hook=_unique)

def _witness(path, offset, raw, kind):
    return {'source_path': str(path), 'byte_offset': offset,
            'raw_line_sha256': hashlib.sha256(raw).hexdigest(), 'kind': kind}

def native_form_reply(path, source_record, text, thread_id):
    """Return verified decoded answers + context, or None without changing input."""
    match = re.fullmatch(r'\s*<'+TAG+r'>\s*(.*?)\s*</'+TAG+r'>\s*', text, re.S)
    if not match: return None
    try:
        rows = _json(match.group(1))
        # A single answer has one exact user quote. Multi-answer envelopes need
        # separate occurrence/quote semantics; preserve them until supported.
        if not isinstance(rows,list) or len(rows) != 1: return None
        identities=[]
        for row in rows:
            if (not isinstance(row,dict) or set(row)!={'questionItemId','question','answer'}
                    or any(not isinstance(row[k],str) or not row[k].strip() for k in row)):
                return None
            identity=_json(row['questionItemId'])
            if (not isinstance(identity,list) or len(identity)!=3 or identity[0]!='request_user_input_async'
                    or not isinstance(identity[1],str) or not identity[1].startswith('call_')
                    or type(identity[2]) is not int or identity[2]<0): return None
            identities.append(tuple(identity))
        if len(set(identities))!=len(identities):return None
        offset=source_record.get('byte_offset');turn=source_record.get('turn_id');mid=source_record.get('message_id')
        if type(offset) is not int or offset<0 or not turn or not mid or source_record.get('session_id')!=thread_id:return None
        with Path(path).open('rb') as stream:
            stream.seek(offset);raw=stream.readline(MAX_LINE+1);receipt_offset=stream.tell();receipt_raw=stream.readline(MAX_LINE+1)
            if len(raw)>MAX_LINE or len(receipt_raw)>MAX_LINE or hashlib.sha256(raw).hexdigest()!=source_record.get('raw_line_sha256'):return None
            original=_json(raw);receipt=_json(receipt_raw);payload=original['payload'];meta=original.get('metadata',{})
            retained=meta.get('retained_source',{});item=receipt['payload']['item']
            content=payload.get('content')
            if (original.get('type')!='response_item' or payload.get('type')!='message' or payload.get('role')!='user'
                    or payload.get('id')!=mid or meta.get('client_authored') is not False
                    or retained.get('complete') is not True
                    or retained.get('id')!={'message_id':mid,'turn_id':turn,'role':'user'}
                    or not isinstance(content,list) or len(content)!=1 or set(content[0])!={'type','text'}
                    or content[0]['type']!='input_text' or content[0]['text'].strip()!=text.strip()
                    or receipt.get('type')!='event_msg' or receipt['payload'].get('type')!='item_completed'
                    or receipt['payload'].get('thread_id')!=thread_id or receipt['payload'].get('turn_id')!=turn
                    or item.get('type')!='UserMessage'
                    or item.get('content')!=[{'type':'text','text':content[0]['text'],'text_elements':[]}]):return None
            witnesses=[_witness(path,offset,raw,'native_answer'),_witness(path,receipt_offset,receipt_raw,'native_user_receipt')]
            wanted={identity[1] for identity in identities};calls={};seen=set();session=None;current_turn=None
            stream.seek(0)
            while stream.tell()<offset:
                at=stream.tell();line=stream.readline(MAX_LINE+1)
                if len(line)>MAX_LINE:return None
                record=_json(line);p=record.get('payload') or {}
                if record.get('type')=='session_meta':session=p.get('id')
                if record.get('type')=='turn_context':current_turn=p.get('turn_id')
                if (record.get('type')!='response_item' or p.get('type')!='function_call'
                        or p.get('call_id') not in wanted):continue
                call_id=p['call_id']
                if call_id in seen:return None
                seen.add(call_id)
                if (session!=thread_id or current_turn!=turn or p.get('name')!='request_user_input_async'
                        or record.get('metadata',{}).get('client_authored') is not False
                        or p.get('internal_chat_message_metadata_passthrough',{}).get('turn_id')!=turn):return None
                args=_json(p['arguments'])
                if not isinstance(args,dict) or set(args)!={'questions'} or not isinstance(args['questions'],list):return None
                questions=args['questions']
                for q in questions:
                    if (not isinstance(q,dict) or set(q)!={'title','options'} or not isinstance(q['title'],str)
                            or not isinstance(q['options'],list) or any(not isinstance(v,str) for v in q['options'])):return None
                next_at=stream.tell();next_raw=stream.readline(MAX_LINE+1)
                if stream.tell()>offset or len(next_raw)>MAX_LINE:return None
                event=_json(next_raw);event_payload=event.get('payload') or {};question_item=event_payload.get('item') or {}
                if (event.get('type')!='event_msg' or event_payload.get('type')!='item_completed'
                        or event_payload.get('thread_id')!=thread_id or event_payload.get('turn_id')!=turn
                        or question_item.get('type')!='AgentMessage' or question_item.get('id')!=call_id
                        or question_item.get('delivery')!='async' or question_item.get('questions')!=questions):return None
                calls[call_id]=questions
                witnesses.extend([_witness(path,at,line,'native_question_call'),_witness(path,next_at,next_raw,'native_question_receipt')])
            for row,identity in zip(rows,identities):
                questions=calls.get(identity[1],[]);index=identity[2]
                if index>=len(questions) or questions[index]['title']!=row['question']:return None
        return {'text':'\n'.join(row['answer'] for row in rows),
                'context':{'schema':'evolving-profile.native-form-answer.v1','questions':[row['question'] for row in rows],
                    'question_authority':'assistant_question_context_not_user_request',
                    'question_item_ids':[row['questionItemId'] for row in rows], 'witnesses':witnesses}}
    except (OSError,ValueError,TypeError,KeyError,AttributeError,IndexError):return None
