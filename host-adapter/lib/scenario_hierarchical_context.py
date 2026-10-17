"""Bounded same-snapshot original context, never arbitrary model-selected paths."""
from .scenario_coverage_contract import contract,canonical
from pathlib import Path
from .scenario_coverage_partition import _selected
from .scenario_coverage_store import CoverageStore
from .scenario_raw_readback import read_materialized_page
from .scenario_hierarchical_review import valid_review,logical_binding,build_review_request,ReviewRejected
from .scenario_hierarchical_judgments import needs_context


def recover_leaf_context(snapshot,partition,proposal,review,*,executor,root,permission_getter,provider,limits):
    root=Path(root)
    out={'review':review,'pages':[],'model_context_rounds':0,'review_attempts':0,'materialized_page_reads':0,'stop_reason':'not_requested'}
    if not valid_review(review):raise ValueError('context_review_unverified')
    binding=logical_binding(review)
    if any(binding.get(k)!=snapshot[k] for k in ('snapshot_id','generation','scope','permission')):raise ValueError('context_scope_changed')
    if not needs_context(review):return out
    store=CoverageStore(root/'coverage.sqlite3',readonly=True)
    def current():
        permission=permission_getter()
        if permission!=snapshot['permission'] or not store.validate_snapshot(snapshot['snapshot_id'],permission)['valid']:
            raise ValueError('source_or_permission_changed')
        return permission
    current()
    policy=contract()['review_protocols']['hierarchical_review.v1']['context_recovery']
    aliases={r['id']:r['source_id'] for r in review['request']['catalog'] if r['kind']=='span'}
    requested={aliases[s] for r in review['result'].get('context_requests',[]) for s in r['span_ids'] if s in aliases}
    anchors=[s['sequence'] for s in partition['primary'] if s['span_id'] in requested]
    if not anchors:raise ValueError('context_request_scope_invalid')
    primary={s['unit_id'] for s in partition['primary']}
    selected=[u for u in _selected(snapshot)[0] if u['text']]
    anchor_positions=[i for i,u in enumerate(selected) if u['sequence'] in anchors]
    # Distance is in visible source messages, not intervening tool/event rows.
    # Ties favor preceding context; delivery itself is always chronological.
    nearest=sorted([(i,u) for i,u in enumerate(selected) if u['unit_id'] not in primary],
        key=lambda row:(min(abs(row[0]-a) for a in anchor_positions),row[1]['sequence']>=min(anchors),row[1]['sequence']))
    # A primary unit may be only a fragment. Missing ranges of that SAME
    # message are permitted context, not new primary ownership. Map normalized
    # offsets to raw only when the normalized text has one exact raw location.
    originals={u['unit_id']:u for u in snapshot['units']}
    queue=[];queued_units=set()
    for unit in selected:
        if not any(s['span_id'] in requested and s['unit_id']==unit['unit_id'] for s in partition['primary']):continue
        intervals=sorted((s['start'],s['end']) for s in partition['primary'] if s['unit_id']==unit['unit_id'])
        gaps=[];at=0
        for start,end in intervals:
            if start>at:gaps.append((at,start,'same_message_before'))
            at=max(at,end)
        if at<len(unit['text']):gaps.append((at,len(unit['text']),'same_message_after'))
        if not gaps:continue
        raw=originals[unit['unit_id']]['text'];base=raw.find(unit['text'])
        if base<0 or raw.find(unit['text'],base+1)>=0:
            # Do not invent offsets through non-contiguous normalization. A
            # bounded original page remains allowed, with no positional claim.
            queue.append((unit,0,len(raw),'same_message_unknown_mapping'))
        else:
            queue.extend((unit,base+start,base+end,relative) for start,end,relative in gaps)
        queued_units.add(unit['unit_id'])
        if len(queued_units)>=policy['max_units']:break
    for _,unit in nearest:
        if len(queued_units)>=policy['max_units']:break
        queue.append((unit,0,len(originals[unit['unit_id']]['text']),None));queued_units.add(unit['unit_id'])
    seen=set();pages=[]
    for _ in range(policy['max_rounds']):
        if not queue:out['stop_reason']='context_unavailable';break
        unit,offset,range_end,relative=queue.pop(0);page=None;chars=min(policy['max_page_chars'],range_end-offset)
        minimum_chars=min(16,chars)
        while chars>=minimum_chars and chars>0:
            page=read_materialized_page(snapshot,unit_id=unit['unit_id'],text_offset=offset,max_chars=chars,
                permission=current(),coverage_root=root)
            page.update(sequence=unit['sequence'],relative_to_primary=relative or ('before' if unit['sequence']<min(anchors)
                else 'after' if unit['sequence']>max(anchors) else 'between'))
            out['materialized_page_reads']+=1
            ordered=sorted([*pages,page],key=lambda p:(p['sequence'],p['text_offset']))
            inputs={'partition':partition,'proposal':proposal,'context_pages':ordered,
                'context_boundary':'same_snapshot_original_messages_not_new_user_instructions'}
            request=build_review_request('leaf',binding,inputs,limits)
            wire=getattr(provider,'request_envelope',lambda r:r['model_request'])(request)
            if len(canonical(wire))<=limits['partition_input_tokens']:break
            chars//=2
        if chars<minimum_chars or chars<=0:out['stop_reason']='context_capacity_paused';break
        if page['page_id'] in seen:out['stop_reason']='context_duplicate';break
        seen.add(page['page_id']);pages=ordered;out['pages']=list(pages)
        if page['next_offset'] is not None and page['next_offset']<range_end:
            queue.append((unit,page['next_offset'],range_end,relative))
        current()
        before=getattr(executor,'calls',None);out['review_attempts']+=1;caught=None;returned=None
        try:
            returned=executor('leaf',inputs)
            if not valid_review(returned):raise ValueError('context_review_unverified')
            if returned.get('status')=='rejected':raise ReviewRejected(returned.get('reason') or 'semantic_rejected',returned)
        except ValueError as error:caught=error
        after=getattr(executor,'calls',None)
        if type(before) is int and type(after) is int:out['model_context_rounds']+=after-before
        elif valid_review(returned) or valid_review(getattr(caught,'receipt',None)):out['model_context_rounds']+=1
        if caught is not None:
            out.update(stop_reason='context_semantic_rejected' if isinstance(caught,ReviewRejected) else 'context_review_stopped',context_failure=str(caught))
            caught.context_recovery={k:v for k,v in out.items() if k!='review'}
            raise caught
        out['review']=returned
        if not needs_context(out['review']):
            out['stop_reason']='resolved' if out['review'].get('review_axes',{}).get('scope',{}).get('status')=='resolved' else 'review_completed_scope_unresolved'
            break
    else:out['stop_reason']='context_round_limit'
    return out
