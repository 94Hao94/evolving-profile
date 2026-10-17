"""Lossless Unicode transport partitions; boundaries do not assert new tasks."""
import re
from .scenario_coverage_contract import fingerprint,contract
from .scenario_source import normalize_scenario_user,_paired_skill_context


def _selected(snapshot):
    if not snapshot.get('source_manifest_complete'):raise ValueError('source_manifest_incomplete')
    selected=[];exclusions=[];previous=None
    for u in snapshot['units']:
        if u['selection']!='visible_message':continue
        text=u['text']
        if u['role']=='user':
            text,excluded=normalize_scenario_user(text)
            for item in excluded:exclusions.append({**item,'unit_id':u['unit_id'],'raw_line_sha256':u['raw_line_sha256']})
            if _paired_skill_context(text,previous,u['turn_id']):
                exclusions.append({'metadata_kind':'native_paired_skill_definition','unit_id':u['unit_id'],'raw_line_sha256':u['raw_line_sha256']})
                previous={'role':u['role'],'text':text,'turn_id':u['turn_id']};continue
        previous={'role':u['role'],'text':text,'turn_id':u['turn_id']}
        selected.append({**u,'text':text,'semantic_text_sha256':fingerprint(text)})
    return selected,exclusions


def _scope_binding(snapshot):
    return fingerprint({k:snapshot.get(k) for k in ('scope','permission','selection_version','normalization_version')})


def _draft_identity(part,scope):
    return fingerprint([scope,part['context_only'],[{k:s.get(k) for k in ('unit_id','role','turn_id','sequence','start','end','text','raw_line_sha256')} for s in part['primary']]])


def _structural_windows(text,capacity):
    start=0
    while start<len(text):
        end=start;used=0
        while end<len(text) and used+len(text[end].encode())<=capacity:
            used+=len(text[end].encode());end+=1
        if end<len(text):
            chunk=text[start:end];floor=start+len(chunk)//2
            # Prefer existing layout, then sentence punctuation. These are
            # transport hints only; never assert a new task or complete intent.
            for pattern in (r'\n\s*\n',r'\n',r'[。！？](?:\s*)|[.!?](?:\s+)'):
                choices=[start+m.end() for m in re.finditer(pattern,chunk) if start+m.end()>=floor]
                if choices:end=choices[-1];break
        yield start,end
        start=end
    if not text:yield 0,0


def partition_snapshot(snapshot,capacity=None,*,context_tokens=None,previous_plan=None,prefer_boundaries=False):
    defaults=contract()['defaults'];capacity=capacity or defaults['partition_input_tokens']
    overlap=defaults['context_tokens'] if context_tokens is None else context_tokens
    if type(capacity) is not int or capacity<4 or type(overlap) is not int or overlap<0 or type(prefer_boundaries) is not bool:raise ValueError('partition_capacity_invalid')
    selected,exclusions=_selected(snapshot)
    # UTF-8 byte count is a conservative transport bound, not a tokenizer claim.
    spans=[]
    for unit in selected:
        text=unit['text'];start=0;end=0;used=0
        if prefer_boundaries:
            spans.extend(_span(snapshot,unit,start,end,text[start:end]) for start,end in _structural_windows(text,capacity))
            continue
        for index,char in enumerate(text):
            size=len(char.encode())
            if used+size>capacity:
                spans.append(_span(snapshot,unit,start,index,text[start:index]));start=index;used=0
            used+=size;end=index+1
        if end>start:spans.append(_span(snapshot,unit,start,end,text[start:end]))
        elif not text:spans.append(_span(snapshot,unit,0,0,''))
    partitions=[];current=[];used=0
    for span in spans:
        size=len(span['text'].encode())
        if current and used+size>capacity:
            partitions.append({'primary':current});current=[];used=0
        current.append(span);used+=size
    if current:partitions.append({'primary':current})
    prior=''
    scope_binding=_scope_binding(snapshot);old_drafts={}
    if (isinstance(previous_plan,dict) and previous_plan.get('scope_binding')==scope_binding
            and previous_plan.get('boundary_preference')==('structural_not_semantic' if prefer_boundaries else None)
            and previous_plan.get('capacity')==capacity and previous_plan.get('context_tokens')==overlap):
        old_drafts={_draft_identity(p,scope_binding):p for p in previous_plan.get('partitions',[])}
    reused=0
    for part in partitions:
        context=''
        for char in reversed(prior):
            if len((char+context).encode())>overlap:break
            context=char+context
        part.update({'context_only':context,'semantic_task_boundary':'unknown','input_counting':'conservative_utf8_bytes',
            'partition_id':fingerprint([snapshot['snapshot_id'],part['primary']]),'snapshot_id':snapshot['snapshot_id']})
        old=old_drafts.get(_draft_identity(part,scope_binding))
        if old:
            # Only exact source text is reused. All identifiers bind the NEW
            # snapshot; no old semantic verdict is copied or promoted.
            part['primary']=[{**current,'text':previous['text']} for current,previous in zip(part['primary'],old['primary'])]
            reused+=1
        part['reused_from_partition_id']=old['partition_id'] if old else None
        part['draft_reuse_basis']='verified_current_raw_units_not_semantic_acceptance' if old else 'new_unreviewed_source_partition'
        prior=''.join(s['text'] for s in part['primary'])
    return {**({'boundary_preference':'structural_not_semantic'} if prefer_boundaries else {}),
        'snapshot_id':snapshot['snapshot_id'],'generation':snapshot['generation'],'partitions':partitions,
        'exclusions':exclusions,'capacity':capacity,'context_tokens':overlap,'scope_binding':scope_binding,
        'reused_partition_drafts':reused,'semantic_review_status':'not_reviewed'}


def _span(snapshot,unit,start,end,text):
    return {'span_id':fingerprint([snapshot['snapshot_id'],unit['unit_id'],start,end]),
        'unit_id':unit['unit_id'],'role':unit['role'],'turn_id':unit['turn_id'],'sequence':unit['sequence'],
        'start':start,'end':end,'text':text,'raw_line_sha256':unit['raw_line_sha256'],
        'text_sha256':fingerprint(text),'transport_span_not_independent_fact':True}


def validate_partition(plan,snapshot):
    if plan.get('snapshot_id')!=snapshot.get('snapshot_id') or plan.get('generation')!=snapshot.get('generation'):
        return {'complete':False,'missing_units':['stale_snapshot']}
    if plan.get('scope_binding')!=_scope_binding(snapshot):return {'complete':False,'missing_units':['scope_binding_changed']}
    selected,exclusions=_selected(snapshot);byid={u['unit_id']:u for u in selected};found={k:[] for k in byid};bad=[]
    sequence=[]
    for part in plan.get('partitions',[]):
        spans=part.get('primary',[])
        if part.get('partition_id')!=fingerprint([snapshot['snapshot_id'],spans]):bad.append('partition_changed')
        for span in spans:
            u=byid.get(span.get('unit_id'))
            if u is None:bad.append('unknown_unit');continue
            start,end=span.get('start'),span.get('end')
            if type(start) is not int or type(end) is not int or not 0<=start<=end<=len(u['text']):bad.append(u['unit_id']);continue
            if span!=_span(snapshot,u,start,end,u['text'][start:end]):bad.append(u['unit_id']);continue
            found[u['unit_id']].append(span);sequence.append((u['sequence'],start))
    if sequence!=sorted(sequence):bad.append('source_order_changed')
    for uid,u in byid.items():
        cursor=0
        for span in found[uid]:
            if span['start']!=cursor:bad.append(uid)
            cursor=span['end']
        if not found[uid] or cursor!=len(u['text']):bad.append(uid)
    if plan.get('exclusions')!=exclusions:bad.append('exclusions_changed')
    return {'complete':not bad,'missing_units':list(dict.fromkeys(bad)),
        'semantic_review_status':'not_reviewed','external_fact_verified':False}


def build_requirement_catalog(plan):
    grouped={};assistants={}
    for part in plan['partitions']:
        for span in part['primary']:
            if span['role']=='assistant':
                a=assistants.setdefault(span['unit_id'],{'unit_id':span['unit_id'],'sequence':span['sequence'],'role':'assistant','text':'','span_ids':[]})
                a['text']+=span['text'];a['span_ids'].append(span['span_id']);continue
            if span['role']!='user' or not span['text']:continue
            row=grouped.setdefault(span['unit_id'],{'requirement_id':fingerprint([plan['snapshot_id'],span['unit_id']]),
                'unit_id':span['unit_id'],'snapshot_id':plan['snapshot_id'],'kind':'unclassified_user_message',
                'status':'unresolved','text':'','spans':[],'partition_ids':[],'sequence':span['sequence'],'role':'user',
                'external_fact_verified':False,'semantic_classification':'unknown'})
            row['text']+=span['text'];row['spans'].append(span['span_id'])
            if part['partition_id'] not in row['partition_ids']:row['partition_ids'].append(part['partition_id'])
    ordered=list(grouped.values())
    for index,row in enumerate(ordered):
        end=ordered[index+1]['sequence'] if index+1<len(ordered) else float('inf')
        row['assistant_context']=[a for a in assistants.values() if row['sequence']<a['sequence']<end]
    return {'snapshot_id':plan['snapshot_id'],'requirements':list(grouped.values()),
        'catalog_kind':'complete_user_message_inventory_not_semantic_intent_extraction',
        'semantic_review_status':'not_reviewed'}
