"""Incremental evidence flow: exact leaves, paged capsules, scoped obligations."""
import json
from pathlib import Path
from .scenario_coverage_contract import fingerprint,hierarchical_protocol_fingerprint
from .scenario_coverage_store import CoverageStore
from .scenario_coverage_partition import validate_partition
from .scenario_coverage_incremental import _provider_binding
from .scenario_hierarchical_store import HierarchicalStore
from .scenario_hierarchical_plan import plan_hierarchical_work
from .scenario_hierarchical_transport import semantic_windows,merge_pages,semantic_descriptor
from .scenario_hierarchical_execution import ReviewExecutor
from .scenario_hierarchical_review import restore_review,logical_inputs,expand_selected_aliases,ReviewRejected,InputCapacityExceeded
from .scenario_intent_atoms import validate_atom_proposal,bind_leaf_review
from .scenario_evidence_capsule import build_capsules
from .scenario_relation_obligations import validate_relation_proposal,assess_hierarchical_scope,obligation_identity_matches
from .scenario_hierarchical_host_planes import host_planes_enabled
from .scenario_raw_readback import read_materialized_page
from .scenario_hierarchical_context import recover_leaf_context
from .scenario_hierarchical_judgments import needs_context
from .scenario_hierarchical_extraction import extract_with_feedback
from .scenario_hierarchical_capacity import prepare_review_work,review_binding
from .scenario_hierarchical_output_recovery import OutputTruncated,split_failed_partition
from .scenario_hierarchical_sources import merge_source_reader
from .scenario_hierarchical_selection import unverified_outcome_notes


def process(job,snapshot,partitions,settings,*,root,provider,budget,permission_getter,scope_getter,
        authorize_request,parent_lease_valid,evaluation_authorization=None):
    from .scenario_hierarchical_incremental import _evaluation_valid,qualification_allows,rebind_unchanged_leaf,compute_invalidation
    root=Path(root);folder=root/'hierarchical';raw_store=CoverageStore(root/'coverage.sqlite3',readonly=True)
    binding=review_binding(snapshot,provider)
    result={'coverage_contract':'hierarchical_review.v1','review_protocol':'hierarchical_review.v1',
        'hierarchical_binding_fingerprint':fingerprint(binding),'snapshot_id':snapshot['snapshot_id'],'generation':snapshot['generation'],
        'status':'local_candidate','model_calls':0,'published':False,'legacy_v3_acceptance':False,
        'external_fact_verified':False,'source_readback':False,'host_delivery':'not_measured','answer_use':'not_measured'}
    if not validate_partition(partitions,snapshot)['complete']:return {**result,'status':'unavailable','reason':'partition_coverage_invalid'}
    def current():return (permission_getter()==snapshot['permission'] and scope_getter()==snapshot['scope']
        and raw_store.validate_snapshot(snapshot['snapshot_id'],permission_getter())['valid']
        and (parent_lease_valid is None or parent_lease_valid()))
    if not current():return {**result,'status':'stale','reason':'source_or_permission_changed'}
    graph_store=HierarchicalStore(folder/'graphs.sqlite3');version=0;previous=None
    try:previous=graph_store.load_current(snapshot['scope'],permission_getter());version=previous['version']
    except ValueError as error:
        if str(error)!='hierarchical_unavailable':raise
    # Compatibility is a read/publication gate, not a paid-execution side effect.
    # Invalidate before any shadow/readiness return can leave old green state.
    if previous and previous['binding']!=binding:
        delta=compute_invalidation(previous['graph'],{'atoms':[],'closure_verified':False},previous['graph'].get('dependencies',{}))
        version=graph_store.mark_stale(snapshot['scope'],delta['stale_ids'],expected_version=version)['version']
    isolated=_evaluation_valid(evaluation_authorization,snapshot,budget) if budget else False
    proof=None;proof_path=folder/'qualification.json'
    if proof_path.is_symlink() or any(p.is_symlink() for p in proof_path.parents):raise ValueError('hierarchical_path_invalid')
    try:
        with proof_path.open('rb') as f:content=f.read(1024*1024+1)
        if len(content)<=1024*1024:proof=json.loads(content)
    except (OSError,ValueError):pass
    if settings['mode']=='source_shadow' or provider is None or budget is None:
        return {**result,'reason':'source_shadow','source_manifest_complete':snapshot['source_manifest_complete']}
    if not isolated and not qualification_allows(proof,binding,settings['limits']):
        return {**result,'reason':'semantic_readiness_unverified'}
    limits=settings['limits'];prepared=prepare_review_work(snapshot,limits,provider,partitions,binding)
    partitions=prepared['partitions']
    if not validate_partition(partitions,snapshot)['complete']:return {**result,'status':'unavailable','reason':'semantic_window_coverage_invalid'}
    plan=prepared['plan']
    executor=ReviewExecutor(binding,limits,folder,provider,budget,current,authorize_request,
        lambda profile:isolated or qualification_allows(proof,{**binding,'provider':_provider_binding(profile)},limits))
    atoms=[];residuals=[];claims=[];leaves=[];discoveries=[];obligations=[];links=[];states=[];capsule=None;raw_pages=0;failure=None;rebound_hits=0
    candidates=[];candidate_residuals=[];candidate_claims=[];leaf_failures=[];context_recovery=[]
    format_repairs=[];output_recovery=[];additional_windows={}
    groups={p['partition_id']:[] for p in partitions['partitions']}
    group_leaves={p['partition_id']:[p['partition_id']] for p in partitions['partitions']};group_discovery={}
    node_tasks={n['node_id']:['pending:'+n['node_id']] for n in plan['merge_nodes']};leaf_ids=list(groups)
    child_ids={p:[] for p in leaf_ids};child_leaves={p:[p] for p in leaf_ids}
    source_units=[u['unit_id'] for u in snapshot['units'] if u['selection']=='visible_message']
    manifest={};coverage={};capacity_recovery=None
    def capture():
        nonlocal manifest,coverage
        required=[t for tasks in node_tasks.values() for t in tasks]
        manifest={'binding':binding,'source_complete':snapshot['source_manifest_complete'],'groups':groups,
            'target_source_unit_ids':source_units,'target_atom_manifest_closed':len(leaves)==len(leaf_ids),
            'atom_ids':[a['atom_id'] for a in atoms],'residual_ids':[a['atom_id'] for a in residuals],
            'claim_ids':[a['atom_id'] for a in claims],
            'unclassified_residual_ids':[a['atom_id'] for a in residuals if a.get('reason')=='unclassified'],
            'leaf_partition_ids':leaf_ids,'discovery_task_ids':required,
            'group_leaf_ids':group_leaves,'group_discovery_ids':group_discovery}
        coverage=assess_hierarchical_scope(manifest,leaves,discoveries,obligations,permission_getter())
        return {'manifest':manifest,'atoms':atoms,'residuals':residuals,'assistant_claims':claims,'capsules':capsule,
            'outcome_notes':unverified_outcome_notes(claims),
            'candidate_atoms':candidates,'candidate_residuals':candidate_residuals,'candidate_claims':candidate_claims,
            'leaf_failures':leaf_failures,'context_recovery':context_recovery,
            'format_repairs':format_repairs,
            'output_recovery':output_recovery,'effective_partitions':partitions,
            'capacity_recovery':capacity_recovery,
            'coverage':coverage,'binding':binding,'leaf_receipts':[dict(r) for r in leaves],
            'discovery_receipts':[dict(r) for r in discoveries],'obligations':obligations,'object_links':links,'states':states,
            'plan':plan,'failure':failure,'dependencies':{c:[n['node_id'] for n in plan['merge_nodes'] if c in n['children']]
                for c in [*leaf_ids,*node_tasks]}}
    def persist():
        nonlocal version
        if not current():raise ValueError('source_or_permission_changed')
        version=graph_store.save_generation(binding,capture(),expected_version=version)['version']
    def consume(receipt,ids,pages=()):
        nonlocal obligations,links,states
        proposed=expand_selected_aliases(receipt['result'],receipt['request'])
        checked=validate_relation_proposal({'atom_ids':ids},proposed,list(pages))
        if checked['errors']:raise ValueError('relation_pending')
        by_id={o['obligation_id']:o for o in obligations}
        for row in checked['obligations']:
            old=by_id.get(row['obligation_id'])
            if old and not obligation_identity_matches(old,row):raise ValueError('relation_pending')
            by_id[row['obligation_id']]=row
        obligations=list(by_id.values());links.extend(checked['object_links'])
        state_map={r['atom_id']:r for r in states};state_map.update({r['atom_id']:r for r in checked['states']});states=list(state_map.values())
    def recover(review,part,proposal):
        try:
            value=recover_leaf_context(snapshot,part,proposal,review,executor=executor,root=root,
                permission_getter=permission_getter,provider=provider,limits=limits)
        except ValueError as error:
            if hasattr(error,'context_recovery'):context_recovery.append({**error.context_recovery,'partition_id':part['partition_id']})
            raise
        context_recovery.append({k:v for k,v in value.items() if k!='review'}|{'partition_id':part['partition_id']})
        return value['review']
    try:
        persist()
        if plan['status']=='capacity_paused':raise ValueError('capacity_paused')
        pending=[(p,0,p['partition_id']) for p in partitions['partitions']]
        while pending:
            part,depth,root_id=pending.pop(0)
            leaf=None
            for saved in (previous or {}).get('graph',{}).get('leaf_receipts',[]):
                original=restore_review(saved,saved['request'],budget)
                rebound=rebind_unchanged_leaf(original,binding,{'partition':part,'units':snapshot['units']}) if original else None
                if rebound:leaf=rebound;rebound_hits+=2;break
            checked=None
            try:
                if leaf is None:
                    extraction,proposal,checked,repairs=extract_with_feedback(snapshot,part,executor)
                    format_repairs.extend(repairs)
                    if checked['errors']:raise ValueError('intent_gap')
                    context_prepared=needs_context(extraction)
                    if context_prepared:
                        contextual=recover(extraction,part,proposal)
                        if contextual.get('stage')=='leaf':leaf=contextual
                    if leaf is None:leaf=executor('leaf',{'partition':part,'proposal':proposal})
                    if needs_context(leaf) and not context_prepared:leaf=recover(leaf,part,proposal)
                else:proposal=logical_inputs(leaf)['proposal']
                value=bind_leaf_review(snapshot,part,proposal,leaf)
                if value['semantic_review_status']!='reviewed':raise ValueError('intent_gap')
                checked=value
            except (OutputTruncated,InputCapacityExceeded) as error:
                if hasattr(error,'format_repairs'):format_repairs.extend(error.format_repairs)
                children=split_failed_partition(snapshot,part,depth=depth,
                    additional_windows=additional_windows.get(root_id,0)) if not isinstance(error,InputCapacityExceeded) or error.stage=='leaf' else None
                failed=({'failed_reservation_id':error.receipt['reservation_id'],
                    'failed_request_sha256':error.receipt['request_sha256'],
                    'failed_response_sha256':error.receipt['response_sha256'],'failure_kind':'output_truncated'}
                    if isinstance(error,OutputTruncated) else {'failed_reservation_id':None,
                    'failed_request_sha256':error.request_sha256,'failed_response_sha256':None,
                    'failure_kind':'input_wire_capacity','actual_wire_bytes':error.wire_bytes})
                output_recovery.append({'partition_id':part['partition_id'],'root_partition_id':root_id,
                    **failed,
                    'depth':depth,'child_partition_ids':[p['partition_id'] for p in children or []],
                    'status':'split' if children else 'capacity_paused','source_scope_reduced':False})
                if not children:persist();raise
                old_id=part['partition_id'];index=next(i for i,p in enumerate(partitions['partitions']) if p['partition_id']==old_id)
                partitions['partitions'][index:index+1]=children
                if not validate_partition(partitions,snapshot)['complete']:raise ValueError('partition_coverage_invalid')
                additional_windows[root_id]=additional_windows.get(root_id,0)+1
                groups.pop(old_id,None);group_leaves.pop(old_id,None);child_ids.pop(old_id,None);child_leaves.pop(old_id,None)
                for child in children:
                    pid=child['partition_id'];groups[pid]=[];group_leaves[pid]=[pid];child_ids[pid]=[];child_leaves[pid]=[pid]
                leaf_ids=[p['partition_id'] for p in partitions['partitions']]
                old_plan=plan
                plan=plan_hierarchical_work(snapshot,partitions,{},
                    {'input_bound':limits['partition_input_tokens'],'output_bound':limits['partition_output_tokens'],'envelope_bytes':0},limits)
                plan['transport_adaptation']=old_plan.get('transport_adaptation')
                plan['review_binding_fingerprint']=old_plan.get('review_binding_fingerprint')
                node_tasks={n['node_id']:['pending:'+n['node_id']] for n in plan['merge_nodes']}
                pending[0:0]=[(p,depth+1,root_id) for p in children]
                persist();continue
            except ValueError as error:
                if hasattr(error,'format_repairs'):format_repairs.extend(error.format_repairs)
                if checked and not checked['errors']:
                    candidates.extend(checked['atoms']);candidate_residuals.extend(checked['residuals']);candidate_claims.extend(checked['assistant_claims'])
                leaf_failures.append({'partition_id':part['partition_id'],'reason':str(error)})
                if not isinstance(error,ReviewRejected) and str(error) not in {'semantic_rejected','attribution_gap','intent_gap','review_has_issues'}:
                    persist();raise
                failure='intent_gap';persist();continue
            leaves.append(leaf);atoms.extend(checked['atoms']);residuals.extend(checked['residuals']);claims.extend(checked['assistant_claims'])
            pid=part['partition_id'];groups[pid]=[a['atom_id'] for key in ('atoms','residuals','assistant_claims') for a in checked[key]]
            child_ids[pid]=groups[pid];persist()
        capsule=build_capsules(binding,atoms,residuals,leaves,limits,claims=claims)
        source_reader=merge_source_reader(snapshot,capsule,root,permission_getter,
            max(1,min(4096,limits['partition_input_tokens']//12)))
        for node in plan['merge_nodes']:
            available={logical_inputs(r)['partition']['partition_id'] for r in leaves}
            if any(not set(child_leaves.get(c,[]))<=available or c not in child_ids for c in node['children']):continue
            ids=list(dict.fromkeys(a for c in node['children'] for a in child_ids[c]))
            owned_leaves=list(dict.fromkeys(a for c in node['children'] for a in child_leaves[c]))
            node_tasks[node['node_id']]=[]
            groups[node['node_id']]=ids;group_leaves[node['node_id']]=owned_leaves
            frontier=[];remaining=list(ids)
            while True:
                page=merge_pages(binding,node,remaining,capsule,obligations,limits,provider,
                    source_reader=source_reader,prior_states=frontier)[0]
                node_tasks[node['node_id']].append(page['task_id'])
                group_discovery[node['node_id']]=[t for n,tasks in node_tasks.items()
                    if n==node['node_id'] or n in node['children'] for t in tasks]
                raw_pages+=len(page.get('source_pages',[]))
                receipt=executor('merge',page);discoveries.append(receipt);consume(receipt,ids,page.get('source_pages',[]))
                frontier=[s for s in states if s['atom_id'] in ids]
                persist()
                consumed={r['atom_id'] for key in ('atoms','residuals','assistant_claims') for r in page[key]}
                remaining=[i for i in remaining if i not in consumed]
                if not remaining:break
                if not consumed:raise ValueError('capsule_ownership_incomplete')
            child_ids[node['node_id']]=ids;child_leaves[node['node_id']]=owned_leaves
        all_items={a['atom_id']:a for a in [*atoms,*residuals,*claims]}
        source_sequences={u['unit_id']:u['sequence'] for u in snapshot['units']}
        capture()
        for obligation in list(coverage['obligations']):
            if obligation['state']!='open':continue
            selected=[all_items[i] for i in obligation['atom_ids']]
            units=list(dict.fromkeys(r['unit_id'] for a in selected for r in a['source_refs']));source_pages=[]
            for unit in units:
                offset=0
                while True:
                    page=read_materialized_page(snapshot,unit_id=unit,text_offset=offset,
                        max_chars=max(1,min(4096,limits['partition_input_tokens']//12)),permission=permission_getter(),coverage_root=root)
                    if host_planes_enabled(binding):page['sequence']=source_sequences[unit]
                    source_pages.append(page)
                    if page['next_offset'] is None:break
                    offset=page['next_offset']
            task_ids=[fingerprint(['readback-page',obligation['obligation_id'],p['page_id']]) for p in source_pages]
            node_tasks['readback:'+obligation['obligation_id']]=task_ids
            for group,gids in groups.items():
                if set(gids)&set(obligation['atom_ids']):group_discovery.setdefault(group,[]).extend(task_ids)
            cited={}
            for task_id,page in zip(task_ids,source_pages):
                evidence=[*cited.values(),page];raw_pages+=1
                receipt=executor('readback',{'task_id':task_id,
                    'atoms':[semantic_descriptor(a) for a in selected if a.get('authority') in {'user_requirement','user_claim'}],
                    'assistant_claims':[semantic_descriptor(a) for a in selected if a.get('authority') in {'assistant_report','assistant_suggestion'}],
                    'residuals':[semantic_descriptor(a) for a in selected if not a.get('authority')],
                    'obligations':[o for o in obligations if o['obligation_id']==obligation['obligation_id']],
                    'source_pages':evidence})
                discoveries.append(receipt);consume(receipt,obligation['atom_ids'],evidence)
                references=[r for o in obligations for r in o.get('evidence_refs',[]) if isinstance(r,dict)]
                for p in evidence:
                    if any(r.get('page_id')==p['page_id'] for r in references):cited[p['page_id']]=p
                persist()
        capture();result.update(status=coverage['status'],coverage=coverage,published=bool(leaves))
        if failure:result['reason']=failure
    except ValueError as error:
        if isinstance(error,InputCapacityExceeded):
            capacity_recovery={'stage':error.stage,'wire_bytes':error.wire_bytes,
                'input_bound':limits['partition_input_tokens'],'request_sha256':error.request_sha256,
                'source_scope_reduced':False,'unprocessed_record_ids':getattr(error,'unprocessed_record_ids',
                    list(obligation['atom_ids']) if error.stage=='readback' else []),
                'next_action':'read_original_or_resume_with_adequate_capacity'}
        allowed={'capacity_paused','budget_paused','parent_attempts_exhausted','intent_gap','relation_pending',
            'source_or_permission_changed','request_already_reserved','provider_failed','parent_lease_expired',
            'parent_lease_required','semantic_rejected'}
        failure=str(error) if str(error) in allowed else 'hierarchical_stage_rejected'
        result.update(status=failure if failure in {'capacity_paused','budget_paused','intent_gap','relation_pending'} else 'unavailable',reason=failure)
    if not current():return {**result,'status':'stale','reason':'source_or_permission_changed','published':False,'model_calls':executor.calls}
    persist()
    return {**result,'coverage':coverage,'model_calls':executor.calls,'reused_review_requests':executor.cache_hits+rebound_hits,
        'outcome_notes':unverified_outcome_notes(claims),
        'budget':budget.status(),'raw_review_pages':raw_pages,'source_manifest_complete':snapshot['source_manifest_complete'],
        'context_recovery':context_recovery,
        'format_repairs':format_repairs,
        'capacity_recovery':capacity_recovery,
        'output_recovery':output_recovery,
        'atom_count':len(atoms),'residual_count':len(residuals),'assistant_claim_count':len(claims)}
