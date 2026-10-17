"""Source-bound semantic proposals. Structural coverage is not understanding."""
from copy import deepcopy
from .scenario_coverage_contract import fingerprint, contract
from .scenario_coverage_partition import _selected


def _quote_with_source_layout(refs,selected):
    pieces=[];previous=None
    for ref in refs:
        if previous and previous['unit_id']==ref['unit_id']:
            gap=selected[ref['unit_id']]['text'][previous['normalized_end']:ref['normalized_start']]
            if gap and gap.isspace():pieces.append(gap)
        pieces.append(ref['quote']);previous=ref
    return ''.join(pieces)


def validate_atom_proposal(snapshot, partition, proposal,*,identity_version='source_offsets.v1',required_roles=('user',)):
    result={'atoms':[],'residuals':[],'assistant_claims':[],'errors':[],
            'semantic_review_status':'not_reviewed','external_fact_verified':False}
    try:
        newer=contract()['review_protocols']['hierarchical_review.v1'].get('selection_wire',{}).get('identity_version')
        if identity_version not in {'source_offsets.v1',newer}:raise ValueError('atom_identity_version_invalid')
        if not isinstance(proposal,dict):raise ValueError('proposal_shape')
        spans={s['span_id']:s for s in partition['primary']}
        selected={u['unit_id']:u for u in _selected(snapshot)[0]}
        originals={u['unit_id']:u for u in snapshot['units']}
        coverage={s['span_id']:[] for s in spans.values() if s['role'] in required_roles and s['text']}
        for span in spans.values():
            unit=selected[span['unit_id']]
            if (unit['role']!=span['role'] or unit['text'][span['start']:span['end']]!=span['text']
                    or unit['raw_line_sha256']!=span['raw_line_sha256']):raise ValueError('span_source_changed')
        seen=set()
        for field in ('atoms','residuals','assistant_claims'):
            if not isinstance(proposal.get(field),list):raise ValueError('proposal_fields')
            for item in proposal[field]:
                if not isinstance(item,dict) or not isinstance(item.get('source_refs'),list) or not item['source_refs']:
                    raise ValueError('atom_source_missing')
                refs=[];prior=None
                for ref in item['source_refs']:
                    if isinstance(ref,dict) and 'quote_source_span' in ref:raise ValueError('atom_reserved_transport_field')
                    span=spans[ref['span_id']]
                    if 'source_selection' in ref:
                        if ref['source_selection']!='entire_span' or any(k in ref for k in ('quote','start','end')):
                            raise ValueError('atom_source_selector_invalid')
                        ref={**ref,'quote':span['text'],'start':0,'end':len(span['text']),'offset_binding':'host_selected_entire_span'}
                    if 'start' not in ref and 'end' not in ref:
                        quote=ref.get('quote')
                        if not isinstance(quote,str) or not quote:raise ValueError('atom_quote_invalid')
                        start=span['text'].find(quote)
                        if start<0 or span['text'].find(quote,start+1)>=0:raise ValueError('atom_quote_ambiguous_or_absent')
                        end=start+len(quote)
                        ref={**ref,'start':start,'end':end,'offset_binding':'host_unique_exact_literal'}
                    else:
                        start,end=ref['start'],ref['end']
                    if (type(start) is not int or type(end) is not int or not 0<=start<end<=len(span['text'])
                            or ref['quote']!=span['text'][start:end]):raise ValueError('atom_quote_invalid')
                    role='assistant' if field=='assistant_claims' else 'user'
                    if span['role']!=role:raise ValueError('atom_authority_or_role')
                    position=(span['sequence'],span['start']+start)
                    if prior is not None and position<prior:raise ValueError('atom_source_order')
                    prior=position
                    normalized=selected[span['unit_id']]['text'];raw=originals[span['unit_id']]['text']
                    base=raw.find(normalized)
                    unique=base>=0 and raw.find(normalized,base+1)<0
                    refs.append({**ref,'unit_id':span['unit_id'],'raw_line_sha256':span['raw_line_sha256'],
                        'role':role,'sequence':span['sequence'],'normalized_start':span['start']+start,'normalized_end':span['start']+end,
                        'normalized_offset_space':'normalized_visible_message_unicode',
                        'message_start':base+span['start']+start if unique else None,
                        'message_end':base+span['start']+end if unique else None,
                        'raw_offset_space':'original_message_unicode' if unique else 'unknown_noncontiguous_or_ambiguous_normalization'})
                    if span['span_id'] in coverage:coverage[span['span_id']].append((start,end))
                if field=='atoms':
                    if item.get('authority') not in {'user_requirement','user_claim'}:raise ValueError('atom_authority_or_role')
                    if (not isinstance(item.get('action'),str) or not item['action'].strip()
                            or type(item.get('negation')) is not bool or not isinstance(item.get('time'),dict)
                            or item.get('kind') not in {'request','constraint','correction','question','confirmation','claim'}):
                        raise ValueError('atom_semantics_missing')
                    for name in ('conditions','exceptions'):
                        if not isinstance(item.get(name),list) or any(not isinstance(v,str) for v in item[name]):
                            raise ValueError('atom_condition_invalid')
                    if not isinstance(item.get('object_hypotheses'),list):raise ValueError('atom_scope_invalid')
                elif field=='assistant_claims':
                    if item.get('authority') not in {'assistant_report','assistant_suggestion'}:raise ValueError('atom_authority_or_role')
                elif item.get('reason') not in {'non_substantive','unclassified'}:raise ValueError('residual_reason_invalid')
                source_group=fingerprint([snapshot['scope'],snapshot['location']['session_id'],
                    [(r['unit_id'],r['raw_line_sha256'],r['normalized_start'],r['normalized_end'],r['role']) for r in refs]])
                stable=fingerprint([snapshot['scope'],snapshot['location']['session_id'],
                    [(r['unit_id'],r['raw_line_sha256'],r['normalized_start'],r['normalized_end'],r['role']) for r in refs],field])
                identity={}
                if identity_version==newer:
                    semantic={k:deepcopy(item[k]) for k in ('kind','authority','action','claim','conditions','negation','exceptions','object_hypotheses','time','local_state','reason') if k in item}
                    stable=fingerprint([identity_version,source_group,field,semantic])
                    identity={'source_group_id':source_group,'identity_version':identity_version}
                if stable in seen:raise ValueError('duplicate_atom')
                seen.add(stable)
                result[field].append({**deepcopy(item),**identity,'source_refs':refs,'source_quote':_quote_with_source_layout(refs,selected),
                    'stable_id':stable,'atom_id':fingerprint([snapshot['snapshot_id'],stable]),
                    'external_fact_verified':False,'semantic_review_status':'not_reviewed'})
        for sid,intervals in coverage.items():
            gap='assistant_character_gap' if spans[sid]['role']=='assistant' else 'intent_character_gap'
            at=0
            for start,end in sorted(intervals):
                if start>at and not spans[sid]['text'][at:start].isspace():raise ValueError(gap)
                at=max(at,end)
            if at<len(spans[sid]['text']) and not spans[sid]['text'][at:].isspace():raise ValueError(gap)
    except (KeyError,TypeError,ValueError,IndexError) as error:
        result['errors']=[str(error) if isinstance(error,ValueError) else 'malformed_proposal']
    return result


def bind_leaf_review(snapshot, partition, proposal, review_receipt):
    try:
        from .scenario_hierarchical_review import valid_review,logical_inputs,logical_binding
        from .scenario_hierarchical_selection import identity_version_from_binding
        valid=valid_review(review_receipt)
    except ImportError:valid=False
    version=identity_version_from_binding(logical_binding(review_receipt)) if valid else 'source_offsets.v1'
    from .scenario_hierarchical_host_planes import source_roles_from_binding
    roles=source_roles_from_binding(logical_binding(review_receipt)) if valid else ('user',)
    value=validate_atom_proposal(snapshot,partition,proposal,identity_version=version,required_roles=roles)
    if (value['errors'] or not valid or review_receipt.get('stage')!='leaf'
            or review_receipt.get('status')!='reviewed'
            or logical_inputs(review_receipt).get('proposal')!=proposal
            or logical_inputs(review_receipt).get('partition')!=partition
            or logical_binding(review_receipt).get('snapshot_id')!=snapshot['snapshot_id']):
        return {**value,'semantic_review_status':'not_reviewed'}
    checked=review_receipt['result']
    axes=review_receipt.get('review_axes')
    if (axes is None and (checked.get('intent_sufficient') is not True or checked.get('conditions_preserved') is not True)
            or axes is not None and axes['attribution']['status']!='sufficient'):
        return {**value,'semantic_review_status':'intent_gap'}
    for key in ('atoms','residuals','assistant_claims'):
        for item in value[key]:
            item['scope_review_status']=axes['scope']['status'] if axes else 'not_reviewed'
            from .scenario_hierarchical_host_planes import host_planes_enabled
            if host_planes_enabled(logical_binding(review_receipt)):
                from .scenario_hierarchical_safety import mark_summary_boundary
                mark_summary_boundary(item)
    return {**value,'semantic_review_status':'reviewed','leaf_receipt_id':review_receipt['request_sha256'],
        'scope_review_status':axes['scope']['status'] if axes else 'not_reviewed'}
