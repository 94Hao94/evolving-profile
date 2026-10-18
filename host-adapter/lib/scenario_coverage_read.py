"""Bounded source-linked coverage pages, not raw source readback or adoption."""
import base64
import json
import os
import uuid
from pathlib import Path

from .scenario_coverage_contract import canonical,fingerprint
from .scenario_coverage_store import CoverageStore


def _read(path,limit):
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError('coverage_path_invalid')
    with os.fdopen(os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)),'rb') as f:raw=f.read(limit+1)
    if len(raw)>limit:raise ValueError('coverage_read_limit')
    return json.loads(raw)


def read_coverage_view(root,session_id,view='overview',*,cursor=None,permission=None,expected_scope=None,requirement_id=None,review_protocol='segment_coverage.v1',expected_review_binding=None):
    sid=str(uuid.UUID(str(session_id)));root=Path(root)
    if review_protocol=='hierarchical_review.v1':
        from .scenario_hierarchical_read import read_hierarchical_view
        return read_hierarchical_view(root,sid,view,cursor=cursor,permission=permission,expected_scope=expected_scope,requirement_id=requirement_id,expected_review_binding=expected_review_binding)
    if review_protocol!='segment_coverage.v1':raise ValueError('coverage_protocol_invalid')
    if view not in {'overview','requirements','relations','source'}:raise ValueError('coverage_view_invalid')
    try:
        status=_read(root/'status'/f'{sid}.json',1024*1024)
        store=CoverageStore(root/'coverage.sqlite3',readonly=True)
        snapshot=store.read(status['snapshot_id'])
    except FileNotFoundError:return {'status':'unavailable','reason':'coverage_not_prepared','source_readback':False}
    if not store.validate_snapshot(snapshot['snapshot_id'],permission)['valid']:raise ValueError('coverage_cursor_stale_source_or_permission')
    if expected_scope and any(snapshot.get('scope',{}).get(k)!=v for k,v in expected_scope.items()):raise ValueError('coverage_scope_changed')
    tags=[status[k] for k in ('review_protocol','coverage_contract') if status.get(k) is not None]
    foreign=next((tag for tag in tags if tag!=review_protocol),None)
    protocol_current=foreign is None
    if not protocol_current:
        # The source inventory is shared, but another protocol's semantic
        # receipt is not. Preserve raw navigation without importing a verdict,
        # conditions, budget, or a fabricated zero-call count for this protocol.
        source_fields=('session_id','attempts','snapshot_id','generation','source_manifest_complete',
            'codec','read_bytes','input_bytes','replayed_bytes','logical_offset','unit_count','selected_count',
            'semantic_user_count','semantic_assistant_count','requirement_count','partition_count','watermark')
        status={**{k:status[k] for k in source_fields if k in status},
            'status':'global_pending' if snapshot['source_manifest_complete'] else 'partial',
            'reason':'review_protocol_changed','semantic_review_status':'not_reviewed',
            'receipt_review_protocol':foreign if isinstance(foreign,str) else 'unknown',
            'model_calls':None,'published':False,'external_fact_verified':False}
    inventory=_read(root/'inventories'/(snapshot['snapshot_id']+'.json'),64*1024*1024) if snapshot['source_manifest_complete'] else {}
    if inventory and (inventory.get('snapshot_id')!=snapshot['snapshot_id'] or inventory.get('generation')!=snapshot['generation']):raise ValueError('coverage_inventory_stale')
    nav={}
    if protocol_current:
        try:nav=_read(root/'navigation'/f'{sid}.json',8*1024*1024)
        except FileNotFoundError:nav={}
        nav_current=bool(nav) and nav.get('snapshot_id')==snapshot['snapshot_id'] and nav.get('generation',snapshot['generation'])==snapshot['generation']
        if nav.get('review_binding') is not None and nav.get('review_binding')!=status.get('review_binding'):nav_current=False
        if not nav_current:nav={}
        if not nav:
            try:nav=_read(root/'review-ledger'/(snapshot['snapshot_id']+'.json'),8*1024*1024)
            except FileNotFoundError:nav={}
            if nav.get('review_binding')!=status.get('review_binding'):nav={}
    binding={'snapshot_id':snapshot['snapshot_id'],'generation':snapshot['generation'],'view':view,
        'review_protocol':review_protocol,'coverage_contract':review_protocol,
        'inventory_sha256':fingerprint(inventory),'navigation_sha256':fingerprint(nav)}
    offset=0;text_offset=0
    if cursor:
        if not isinstance(cursor,str) or len(cursor)>4096:raise ValueError('coverage_cursor_invalid')
        try:
            data=json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if any(data.get(k)!=v for k,v in binding.items()):raise ValueError()
            offset,text_offset=data['offset'],data['text_offset']
            if type(offset) is not int or type(text_offset) is not int or min(offset,text_offset)<0:raise ValueError()
        except Exception:raise ValueError('coverage_cursor_stale_or_invalid') from None
    result={**status,**binding,'raw_source_status':'not_read','source_readback':False,'host_delivery':'not_measured',
        'has_unread_requirements':status.get('requirement_count',0)>0,'requires_readback':True}
    requirements=inventory.get('requirements',{}).get('requirements',[])
    if view=='requirements':
        if offset>len(requirements):raise ValueError('coverage_cursor_invalid')
        starts_at_origin=offset==0 and text_offset==0
        out=[];chars=0
        while offset<len(requirements) and len(out)<10 and chars<4096:
            req=requirements[offset];text=req['text']
            if text_offset>len(text):raise ValueError('coverage_cursor_invalid')
            chunk=text[text_offset:text_offset+4096-chars]
            states=nav.get('coverage',{}).get('requirement_states',{}) if nav.get('coverage',{}).get('status')=='accepted' else {}
            assistant=req.get('assistant_context',[])
            intents=[i for i in nav.get('intent_ledger',[]) if i.get('requirement_id')==req['requirement_id']]
            out.append({**{k:req.get(k) for k in ('requirement_id','unit_id','snapshot_id','role','sequence','kind')},
                'status':states.get(req['requirement_id'],req.get('status','unresolved')),
                'text':chunk,'text_offset':text_offset,'text_total_chars':len(text),
                'partition_count':len(req.get('partition_ids',[])),'span_count':len(req.get('spans',[])),
                'assistant_context_count':len(assistant),'has_unread_assistant_context':bool(assistant),
                'assistant_context_locators':[{'unit_id':a['unit_id'],'sequence':a['sequence'],'role':'assistant'} for a in assistant[:3]],
                'intent_count':len(intents),'intents':[{'intent_id':i['intent_id'],'kind':i['kind'],'status':i['status'],
                    'source_quote':i['source_quote'][:512],'has_unread_source_quote':len(i['source_quote'])>512,
                    'source_locator':i['source_locator']} for i in intents[:3]],
                'source_locator':(intents[0]['source_locator'] if intents else _unit_locator(snapshot,req['unit_id'])),
                'requires_source_readback':True})
            chars+=len(chunk);text_offset+=len(chunk)
            if text_offset<len(text):break
            offset+=1;text_offset=0
        more=offset<len(requirements)
        result.update(requirements=out,coverage_cursor=base64.urlsafe_b64encode(canonical({**binding,'offset':offset,'text_offset':text_offset})).decode() if more else None,
            has_unread_requirements=more or not starts_at_origin,has_more_requirements_after_page=more,
            all_requirements_in_this_response=starts_at_origin and not more,
            requirements_total=len(requirements),reading_state_scope='this_response_not_host_attention_or_prior_pages')
    elif view=='relations':
        relations=nav.get('coverage',{}).get('relations',[])
        if offset>len(relations):raise ValueError('coverage_cursor_invalid')
        page=[]
        for relation in relations[offset:offset+20]:
            projected={k:relation[k] for k in ('type','from','to') if isinstance(relation.get(k),str)}
            quote=relation.get('evidence_quote','')
            if isinstance(quote,str):projected.update(evidence_quote=quote[:512],has_unread_relation_details=len(quote)>512)
            page.append(projected)
        next_offset=offset+len(page)
        result.update(relations=page,relations_total=len(relations),coverage_cursor=base64.urlsafe_b64encode(canonical({**binding,'offset':next_offset,'text_offset':0})).decode() if next_offset<len(relations) else None,
            relations_coverage=('accepted_receipt_only' if nav.get('coverage',{}).get('status')=='accepted' else 'partial_or_unverified_receipt') if nav else 'not_reviewed')
    elif view=='source':
        if cursor:raise ValueError('source_view_does_not_accept_cursor')
        req=next((r for r in requirements if r['requirement_id']==requirement_id),None)
        if req is None:raise ValueError('source_requirement_scope_unverified')
        from .raw_session_evidence import read_evidence
        unit=next(u for u in snapshot['units'] if u['unit_id']==req['unit_id'])
        raw=read_evidence(sid,snapshot['location']['root'],turn_id=unit['turn_id'],coverage_root=root,max_chars=12000,raw_line_sha256=unit['raw_line_sha256'])
        result.update(raw_source_status=raw['status'],raw_source=raw.get('source',{}),raw_source_coverage=raw.get('coverage',{}),
            source_readback=raw['status']=='source_read' and bool(raw.get('source',{}).get('text')),coverage_cursor=None)
    else:
        result['coverage_cursor']=None
        result['watermark']=snapshot['checkpoint']
        result['current_conditions']=nav.get('current_conditions',[])[:3]
        result['historical_conditions']=nav.get('historical_conditions',[])[:3]
        result['unresolved_conditions']=nav.get('unresolved_conditions',[])[:3]
        result['scope']=snapshot['scope']
    if len(canonical(result))>192*1024:raise ValueError('coverage_page_serialized_limit')
    return result


def _unit_locator(snapshot,unit_id):
    from .scenario_intent_ledger import source_locator
    return source_locator(snapshot,next(u for u in snapshot['units'] if u['unit_id']==unit_id))
