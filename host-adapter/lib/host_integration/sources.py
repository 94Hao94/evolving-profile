"""Versioned visible-message parsing. Canonical records are not raw byte witnesses."""
import hashlib
import json


def parse_host_source(records,parser_id,binding):
    result={'schema':'ep.host-source.v1','parser_id':parser_id,'messages':[],
            'complete':False,'status':'unknown_format','gaps':[]}
    if parser_id not in ('claude_messages.v1','codex.v1'):return result
    if binding.get('attestation')!='trusted_entry':return {**result,'status':'unattested_source'}
    if not isinstance(records,list):return {**result,'status':'invalid_source'}
    result['status']='parsed';seen=set()
    for index,row in enumerate(records):
        if not isinstance(row,dict):result['gaps'].append({'index':index,'reason':'invalid_record'});continue
        source_session=row.get('sessionId') if parser_id=='claude_messages.v1' else row.get('payload',{}).get('session_id')
        if source_session and source_session!=binding.get('session_id'):
            result['gaps'].append({'index':index,'reason':'foreign_session'});continue
        if row.get('type') in ('summary','compacted','compact_boundary') or row.get('isCompactSummary'):
            result['gaps'].append({'index':index,'reason':'compressed_gap'});continue
        if parser_id=='claude_messages.v1':
            message=row.get('message')
        else:
            message=row.get('payload') if row.get('type')=='response_item' else None
            if isinstance(message,dict) and message.get('type')!='message':message=None
        if not isinstance(message,dict):
            if row.get('type') not in ('session_meta','turn_context','event_msg','system'):
                result['gaps'].append({'index':index,'reason':'unrecognized_record'})
            continue
        role=message.get('role');content=message.get('content');parts=[];tool=False
        if role not in ('user','assistant','tool'):continue
        if isinstance(content,str):parts=[content]
        elif isinstance(content,list):
            for block in content:
                if not isinstance(block,dict):continue
                if block.get('type') in ('text','input_text','output_text') and isinstance(block.get('text'),str):parts.append(block['text'])
                if block.get('type')=='tool_result':tool=True
        if tool:role='tool';parts=[]
        if row.get('isMeta') is True or message.get('isMeta') is True:role='system'
        if role=='system':continue
        native_id=row.get('uuid') or row.get('id')
        if native_id and native_id in seen:continue
        if native_id:seen.add(native_id)
        canonical=json.dumps(row,ensure_ascii=False,sort_keys=True).encode()
        if parts or tool:
            result['messages'].append({'role':role,'content':'\n'.join(parts),
                'authority':'user_statement' if role=='user' else 'assistant_report' if role=='assistant' else 'tool_result',
                'source_record':{'index':index,'native_id':native_id,'session_id':binding.get('session_id'),
                    'host_id':binding.get('host_id'),'record_sha256':hashlib.sha256(canonical).hexdigest(),
                    'hash_semantics':'canonical_json_not_raw_bytes','raw_bytes_verified':False}})
    # Only the caller can attest complete original transport, never this parser.
    result['complete']=False
    result['coverage']='parsed_visible_records_not_full_original_source'
    return result
