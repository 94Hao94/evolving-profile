"""Declared discovery/relationship coverage, never exhaustive no-conflict proof."""
from .scenario_coverage_contract import fingerprint,contract
from .scenario_hierarchical_review import valid_review,logical_binding,logical_inputs,expand_selected_aliases


def obligation_identity_matches(old,row):
    keys=('relation_kind','record_kind','from_item','to_item')
    return set(old['atom_ids'])==set(row['atom_ids']) and all(old.get(k)==row.get(k) for k in keys)


def build_discovery_tasks(binding,capsules,prior_states):
    ids=[r['atom_id'] for r in [*capsules.get('atoms',[]),*capsules.get('residuals',[])]]
    if len(set(ids))!=len(ids):raise ValueError('discovery_duplicate_atom')
    boundaries=capsules.get('boundaries',[])
    task={'binding':binding,'required_ids':ids,'boundaries':boundaries,'prior_states':prior_states}
    return {**task,'task_id':fingerprint(task),'semantic_discovery_assurance':'model_may_miss_relations',
        'cross_scope_exhaustiveness':'not_exhaustive'}


def validate_relation_proposal(task,response,evidence):
    out={'obligations':[],'object_links':[],'states':[],'errors':[]};ids=set(task['atom_ids']);seen=set()
    pages={r['page_id']:r for r in evidence if isinstance(r,dict) and r.get('source_readback') is True}
    try:
        rows=response['obligations'];links=response['object_links']
        if not isinstance(rows,list) or not isinstance(links,list):raise ValueError('relation_shape_invalid')
        for row in rows:
            if not isinstance(row,dict):raise ValueError('relation_shape_invalid')
            targets=row['atom_ids'];state=row['state'];refs=row.get('evidence_refs',[])
            identity=row.get('obligation_id')
            if identity is not None and (not isinstance(identity,str) or not identity or len(identity)>256):raise ValueError('relation_id_invalid')
            identity=identity or fingerprint([targets,row.get('reason')])
            if identity in seen:raise ValueError('relation_duplicate_id')
            seen.add(identity)
            if (not isinstance(targets,list) or not targets or any(not isinstance(i,str) for i in targets)
                    or not set(targets)<=ids or not isinstance(row.get('reason'),str)
                    or state not in {'open','supported','refuted','not_applicable'} or not isinstance(refs,list)):
                raise ValueError('relation_scope_invalid')
            proof=bool(refs)
            for ref in refs:
                page=pages.get(ref.get('page_id')) if isinstance(ref,dict) else None
                quote=ref.get('quote') if isinstance(ref,dict) else None
                proof=proof and page is not None and isinstance(quote,str) and bool(quote.strip()) and quote in page['text']
            metadata={}
            registry=contract()['review_protocols']['hierarchical_review.v1']['selection_wire']
            if 'relation_kind' in row:
                kind=row['relation_kind'];first=row.get('from_item');last=row.get('to_item')
                if (not isinstance(kind,str) or kind not in registry['relation_kinds'] or first==last
                        or targets!=[first,last] or 'record_kind' in row):raise ValueError('relation_scope_invalid')
                metadata={'relation_kind':kind,'from_item':first,'to_item':last}
            elif 'from_item' in row or 'to_item' in row:raise ValueError('relation_scope_invalid')
            elif 'record_kind' in row:
                kind=row['record_kind']
                if not isinstance(kind,str) or kind not in registry['record_obligation_kinds']:raise ValueError('relation_scope_invalid')
                metadata={'record_kind':kind}
            if row.get('identity_verification')=='model_hypothesis_only':
                metadata.update(identity_verification='model_hypothesis_only',
                    model_reported_state=row.get('model_reported_state','open'))
                state='open'
            out['obligations'].append({'obligation_id':identity,**metadata,
                'atom_ids':targets,'state':state if proof or state=='open' else 'open','reason':row['reason'],
                'evidence_refs':refs,'evidence_supported':bool(proof)})
        # Object identity links need explicit source-bound quote evidence, not a
        # label produced by semantic similarity or the same institution/cwd.
        for link in links:
            if not isinstance(link,dict):raise ValueError('object_link_shape_invalid')
            targets=link.get('atom_ids');refs=link.get('source_refs')
            if (isinstance(targets,list) and all(isinstance(i,str) for i in targets) and set(targets)<=ids
                    and len(targets)>=2 and isinstance(refs,list) and refs
                    and all(isinstance(r,dict) and r.get('page_id') in pages and isinstance(r.get('quote'),str)
                        and r['quote'].strip() and r['quote'] in pages[r['page_id']]['text'] for r in refs)):
                out['object_links'].append(link)
            else:out['errors'].append('object_link_unverified')
        states=response.get('group_states',[])
        if not isinstance(states,list):raise ValueError('state_shape_invalid')
        state_targets=set()
        for row in states:
            if (not isinstance(row,dict) or not isinstance(row.get('atom_id'),str) or row['atom_id'] not in ids
                    or row.get('state') not in {'current','historical','unresolved','reported'}):raise ValueError('state_scope_invalid')
            if row['atom_id'] in state_targets:raise ValueError('state_duplicate_target')
            state_targets.add(row['atom_id']);refs=row.get('evidence_refs',[])
            if not isinstance(refs,list):raise ValueError('state_shape_invalid')
            proof=bool(refs) and all(isinstance(r,dict) and r.get('page_id') in pages and isinstance(r.get('quote'),str)
                and r['quote'].strip() and r['quote'] in pages[r['page_id']]['text'] for r in refs)
            out['states'].append({**row,'verification':'source_readback_supported' if proof else 'model_proposal_only',
                'external_fact_verified':False})
    except (KeyError,TypeError,ValueError) as error:
        out['errors'].append(str(error) if isinstance(error,ValueError) else 'relation_shape_invalid')
    return out


def assess_hierarchical_scope(manifest,leaf_receipts,discovery_receipts,obligations,permission):
    binding=manifest['binding']
    def usable(r,stage):
        return (valid_review(r) and r.get('status')=='reviewed' and r.get('stage') in stage
            and all(logical_binding(r).get(k)==v for k,v in binding.items()))
    leaves={logical_inputs(r)['partition']['partition_id'] for r in leaf_receipts if usable(r,{'leaf'})}
    scope_pending={logical_inputs(r)['partition']['partition_id'] for r in leaf_receipts if usable(r,{'leaf'})
        and r.get('review_axes') and r['review_axes']['scope']['status']!='resolved'}
    discoveries={r['request']['inputs'].get('task_id'):r for r in discovery_receipts if usable(r,{'merge','readback'})}
    required_tasks=set(manifest.get('discovery_task_ids',[]))
    pending_tasks={key for key,r in discoveries.items() if key in required_tasks and r.get('review_axes')
        and r['review_axes']['scope']['status']!='resolved'}
    scope_issues=[{'stage':r['stage'],'request_sha256':r['request_sha256'],'scope':r['review_axes']['scope']}
        for r in [*leaf_receipts,*discoveries.values()] if usable(r,{'leaf','merge','readback'})
        and r.get('review_axes') and r['review_axes']['scope']['status']!='resolved']
    known=set(manifest.get('atom_ids',[]))|set(manifest.get('residual_ids',[]))|set(manifest.get('claim_ids',[]))
    observed=set()
    for r in discoveries.values():
        observed.update(i['atom_id'] for i in [*r['request']['inputs'].get('atoms',[]),*r['request']['inputs'].get('residuals',[]),*r['request']['inputs'].get('assistant_claims',[])])
    discovered=set(manifest.get('discovery_task_ids',[]))<=set(discoveries) and known<=observed
    leaf_complete=bool(leaves) and set(manifest.get('leaf_partition_ids',[]))<=leaves and manifest.get('target_atom_manifest_closed',True) is True
    source=manifest.get('source_complete') is True and permission.get('allowed') is True
    evidence=[p for r in discoveries.values() for p in r['request']['inputs'].get('source_pages',[])]
    # Reconstruct the obligation chain from verified model responses. Callers
    # cannot hide a model-reported open obligation by passing an empty list.
    chain={};chain_errors=[]
    for receipt in discoveries.values():
        try:proposed=expand_selected_aliases(receipt['result'],receipt['request'])
        except (ValueError,TypeError,KeyError):
            chain_errors.append('relation_source_selector_invalid');continue
        evaluated=validate_relation_proposal({'atom_ids':list(known)},proposed,
            receipt['request']['inputs'].get('source_pages',[]))
        chain_errors.extend(evaluated['errors'])
        for row in evaluated['obligations']:
            old=chain.get(row['obligation_id'])
            if old and not obligation_identity_matches(old,row):chain_errors.append('obligation_identity_changed')
            else:chain[row['obligation_id']]=row
    for row in obligations:
        if row.get('obligation_id') not in chain:chain[row.get('obligation_id')]=dict(row,state='open')
    checked=validate_relation_proposal({'atom_ids':list(known)},{'obligations':list(chain.values()),'object_links':[]},evidence)
    checked['errors'].extend(chain_errors)
    terminal=set(contract()['review_protocols']['hierarchical_review.v1']['obligation_terminal_states'])
    open_rows=[o for o in checked['obligations'] if o['state'] not in terminal]
    groups={}
    for key,group in manifest.get('groups',{}).items():
        group_ids=set(group)
        needed_leaves=set(manifest.get('group_leaf_ids',{}).get(key,manifest.get('leaf_partition_ids',[])))
        needed_discovery=set(manifest.get('group_discovery_ids',{}).get(key,manifest.get('discovery_task_ids',[])))
        complete=(source and bool(needed_leaves) and needed_leaves<=leaves and needed_discovery<=set(discoveries)
            and group_ids<=observed and not checked['errors'])
        ambiguous=bool(needed_leaves&scope_pending or needed_discovery&pending_tasks) or any(group_ids&set(o['atom_ids']) for o in open_rows)
        gap=bool(group_ids&set(manifest.get('unclassified_residual_ids',[])))
        status='scope_reviewed' if complete and not ambiguous and not gap else 'intent_gap' if gap or not source or not needed_leaves<=leaves else 'relation_pending'
        groups[key]={'status':status,'navigation_allowed':permission.get('allowed') is True,
            'guidance_verified':False,'requires_source_readback':True}
    target=bool(groups) and source and leaf_complete and discovered and all(g['status']=='scope_reviewed' for g in groups.values())
    axis_receipts=[r for r in leaf_receipts if usable(r,{'leaf'})]+[r for key,r in discoveries.items() if key in required_tasks]
    axes_complete=leaf_complete and discovered and bool(axis_receipts) and all(r.get('review_axes') is not None for r in axis_receipts)
    result={'coverage_contract':'hierarchical_review.v1','status':'scope_reviewed' if target else 'relation_pending' if leaf_complete else 'intent_gap',
        'groups':groups,'target_complete':target,'source_coverage':'complete' if source else 'partial',
        'intent_review':'complete' if leaf_complete and not manifest.get('unclassified_residual_ids') else 'partial',
        'attribution_review':'complete' if leaf_complete and not manifest.get('unclassified_residual_ids') else 'partial',
        'scope_review':'unresolved' if scope_pending or pending_tasks or open_rows else 'resolved' if axes_complete else 'not_reviewed',
        'scope_axes_complete':axes_complete,'scope_issues':scope_issues,
        'scope_pending_leaf_count':len(scope_pending),
        'obligation_review':'complete' if discovered and not open_rows and not checked['errors'] else 'partial',
        'discovery_procedure_coverage':'complete' if discovered else 'partial','semantic_discovery_assurance':'model_may_miss_relations',
        'discovered_obligation_resolution':'complete' if not open_rows and not checked['errors'] else 'partial',
        'cross_scope_exhaustiveness':'not_exhaustive','task_outcome':'not_verified','external_fact_verified':False,
        'unresolved_count':len(open_rows)+len(scope_pending)+len(pending_tasks),'unread_count':len(known-observed),'obligations':checked['obligations'],
        'errors':checked['errors'],'source_readback':False,'host_delivery':'not_measured','answer_use':'not_measured',
        'leaf_count':len(leaves),'discovery_count':len(discoveries)}
    from .scenario_hierarchical_host_planes import host_planes_enabled
    if host_planes_enabled(binding):
        from .scenario_hierarchical_safety import mark_summary_boundary
        mark_summary_boundary(result)
    return result
