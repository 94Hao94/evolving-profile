"""Explicit scoped coverage work; defaults to structural shadow with zero HTTP.

The original summary job and its attempts are never rewritten here. One decoder
is owned by the worker across bounded leases; restart replays a checked prefix.
"""
from . import platform_lock as fcntl
import json
import os
import re
import tempfile
from pathlib import Path

from .scenario_coverage_budget import CoverageBudget
from .scenario_coverage_contract import canonical,fingerprint,validate_settings
from .scenario_coverage_partition import partition_snapshot,validate_partition,build_requirement_catalog
from .scenario_coverage_store import CoverageStore,freeze_snapshot
from .scenario_source_codec import locate_source,open_source_stream,read_source_batch


def invalidate_dependents(previous,current):
    old={u['unit_id'] for u in previous.get('units',[])};new={u['unit_id'] for u in current.get('units',[])}
    return {'changed_units':sorted(old^new),'reusable_raw_unit_ids':sorted(old&new),
        'global_review_invalidated':True,'semantic_acceptance_reused':False}


def _write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.coverage-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def process_coverage_job(job,source,config,*,store_root,provider=None,max_leases=64,permission_getter=None,scope_getter=None,authorize_request=None,parent_lease_valid=None):
    settings=validate_settings(config);calls=0
    base={'session_id':job['session_id'],'attempts':job.get('attempts'),'mode':settings['mode'],
        'model_calls':0,'published':False,'external_fact_verified':False,'source_readback':False}
    if (job.get('status')=='protected' or not job.get('bank_id') or not job.get('project_key')
            or job.get('permission',{}).get('allowed') is not True):
        return {**base,'status':'unavailable','reason':'scope_or_permission_unverified'}
    permission_getter=permission_getter or (lambda:job['permission'])
    scope={'session_id':job['session_id'],'bank_id':job['bank_id'],'project_key':job['project_key'],
        'identity_kind':'session_scoped_workspace_navigation_only'}
    scope_getter=scope_getter or (lambda:scope)
    permission=permission_getter()
    if permission!=job['permission']:return {**base,'status':'unavailable','reason':'permission_changed'}
    if type(max_leases) is not int or not 1<=max_leases<=64:raise ValueError('coverage_lease_limit_invalid')
    root=Path(store_root)
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):raise ValueError('coverage_path_invalid')
    root.mkdir(parents=True,exist_ok=True)
    fd=os.open(root/'decoder.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {**base,'status':'partial','reason':'decoder_busy'}
        loc=locate_source(job['session_id'],source)
        if loc['status']!='ready':return {**base,'status':'unavailable','reason':loc['status']}
        if scope_getter()!=scope:return {**base,'status':'unavailable','reason':'scope_changed'}
        snap=freeze_snapshot(loc,permission,scope=scope);store=CoverageStore(root/'coverage.sqlite3');state=store.create_snapshot(snap)
        prior_status={}
        try:prior_status=json.loads((root/'status'/f"{job['session_id']}.json").read_text())
        except (OSError,ValueError):pass
        total_read=0;total_input=0;replayed=0;reason=None;terminal_status=None
        if not state['source_manifest_complete']:
            limits=settings['limits']
            with open_source_stream(loc,checkpoint=state['checkpoint'],
                    permission=lambda:permission_getter()==permission,max_line_bytes=limits['line_bytes']) as stream:
                for _ in range(max_leases):
                    if scope_getter()!=scope:return {**base,'status':'unavailable','reason':'scope_changed'}
                    batch=read_source_batch(stream,limits={k:limits[k] for k in ('input_bytes','output_bytes','wall_seconds')})
                    total_read+=batch['read_bytes'];total_input+=batch['input_bytes'];replayed=batch['replayed_bytes']
                    reason=batch['reason']
                    terminal_status=batch['status'] if batch['status'] in {'invalid','unavailable'} else None
                    from .retention_policy import retention_turns
                    from .scenario_source import normalize_scenario_user,_paired_skill_context
                    policy_messages=[];previous=None
                    for unit in [*state['units'],*batch['units']]:
                        if unit['selection']!='visible_message':continue
                        text=normalize_scenario_user(unit['text'])[0] if unit['role']=='user' else unit['text']
                        message={'role':unit['role'],'text':text,'content':text,'turn_id':unit['turn_id']}
                        paired=unit['role']=='user' and _paired_skill_context(text,previous,unit['turn_id'])
                        previous=message
                        if text and not paired:policy_messages.append(message)
                    if any(t['write_policy']['knowledge_allowed'] is False for t in retention_turns(policy_messages)):
                        result={**base,'status':'unavailable','reason':'source_knowledge_write_prohibited'}
                        _write(root/'status'/f"{job['session_id']}.json",result)
                        return result
                    # During replay the last durable checkpoint is ahead of the
                    # decoder; do not replace it with an earlier prefix.
                    if stream.replay_done and batch['source_identity_verified']:
                        if not store.validate_snapshot(snap['snapshot_id'],permission_getter())['valid'] or scope_getter()!=scope:
                            return {**base,'status':'unavailable','reason':'source_scope_or_permission_changed'}
                        state=store.append_source_batch(snap['snapshot_id'],batch,expected_version=state['generation'],permission=permission_getter())
                    if batch['status'] in {'complete','invalid','unavailable'} or reason in {'line_limit','incomplete_record','unsupported_message_schema'}:break
                    if total_read>=limits['spool_source_bytes'] or total_input>=limits['spool_source_bytes']:
                        reason='source_resource_limit';break
        result={**base,'snapshot_id':snap['snapshot_id'],'generation':state['generation'],
            'source_manifest_complete':state['source_manifest_complete'],'semantic_review_status':'not_reviewed',
            'codec':loc['codec'],'read_bytes':total_read,'input_bytes':total_input,'replayed_bytes':replayed,
            'logical_offset':(state['checkpoint'] or {}).get('logical_offset',0),'reason':reason,
            'unit_count':state['unit_count'],'selected_count':state['selected_count'],
            'semantic_budget_identity':state['semantic_budget_identity']}
        if not state['source_manifest_complete']:
            result['status']=terminal_status or 'partial';_write(root/'status'/f"{job['session_id']}.json",result);return result
        def cached_inventory(snapshot_id):
            if not isinstance(snapshot_id,str) or not re.fullmatch('[0-9a-f]{64}',snapshot_id):return None
            path=root/'inventories'/(snapshot_id+'.json')
            if path.is_symlink():return None
            try:
                with path.open('rb') as f:raw=f.read(64*1024*1024+1)
                if len(raw)>64*1024*1024:return None
                return json.loads(raw)
            except (OSError,ValueError):return None
        current_inventory=cached_inventory(state['snapshot_id']);plan=(current_inventory or {}).get('partition_plan')
        plan_reused=bool(plan and plan.get('capacity')==settings['limits']['partition_input_tokens']
            and plan.get('context_tokens')==settings['limits']['context_tokens'] and validate_partition(plan,state)['complete'])
        if not plan_reused:
            previous=cached_inventory(prior_status.get('snapshot_id'))
            plan=partition_snapshot(state,capacity=settings['limits']['partition_input_tokens'],context_tokens=settings['limits']['context_tokens'],
                previous_plan=(previous or {}).get('partition_plan'))
        structural=validate_partition(plan,state);requirements=build_requirement_catalog(plan)
        semantic_roles={s['unit_id']:s['role'] for p in plan['partitions'] for s in p['primary'] if s['text']}
        if not structural['complete']:raise ValueError('partition_coverage_invalid')
        result.update({'status':'global_pending','partition_count':len(plan['partitions']),
            'partition_draft_cache_reused':plan_reused,
            'requirement_count':len(requirements['requirements']),'reason':'model_trial_disabled',
            'semantic_user_count':sum(r=='user' for r in semantic_roles.values()),
            'semantic_assistant_count':sum(r=='assistant' for r in semantic_roles.values()),
            'has_unread_requirements':bool(requirements['requirements']),'requires_readback':True})
        # Persist source inventory separately from accepted navigation. No legacy
        # context-index row is replaced by a structural or locally green result.
        inventory={'snapshot_id':snap['snapshot_id'],'generation':state['generation'],'requirements':requirements,'partition_plan':plan}
        _write(root/'inventories'/(snap['snapshot_id']+'.json'),inventory)
        _write(root/'inventories'/f"{job['session_id']}.json",inventory)
        if prior_status.get('snapshot_id') and prior_status['snapshot_id']!=state['snapshot_id']:
            previous=store.read(prior_status['snapshot_id']);delta=invalidate_dependents(previous,state)
            result['incremental']={'changed_unit_count':len(delta['changed_units']),
                'reused_source_units':len(delta['reusable_raw_unit_ids']),'global_review_invalidated':True,
                'reused_partition_drafts':plan.get('reused_partition_drafts',0),
                'semantic_acceptance_reused':False}
        if settings['review_protocol']=='hierarchical_review.v1':
            from .scenario_hierarchical_incremental import dispatch_hierarchical
            result=dispatch_hierarchical(job,state,settings,provider,root,permission_getter,scope_getter,
                authorize_request,parent_lease_valid,result)
        elif settings['limits']['model_requests'] and provider is not None and requirements['requirements']:
            if getattr(provider,'requires_parent_lease',False) and authorize_request is None:
                result.update(status='unavailable',reason='parent_lease_required')
            else:result=_run_model_stages(job,state,plan,requirements,settings,provider,root,store,permission_getter,result,scope_getter,authorize_request,parent_lease_valid)
        _write(root/'status'/f"{job['session_id']}.json",result)
        return result
    finally:os.close(fd)


def _provider_binding(provider):
    if isinstance(getattr(provider,'review_identity',None),dict):return provider.review_identity
    config=getattr(provider,'config',{})
    return {'protocol':'segmented-provider-review.v1','model':config.get('EVOLVING_PROFILE_API_LLM_MODEL','unknown'),
        'base_url':config.get('EVOLVING_PROFILE_API_LLM_BASE_URL','unknown')}


def _run_model_stages(job,state,plan,requirements,settings,provider,root,store,permission_getter,result,scope_getter,authorize_request=None,parent_lease_valid=None):
    from .scenario_coverage_review import local_payload,review_partition,restore_local_review
    from .scenario_global_review import plan_global_review,global_payload,review_global_partition,validate_global_coverage,restore_global_part
    from .scenario_coverage_publish import publish_segmented_navigation
    alternatives=getattr(provider,'fallback_providers',lambda:[])()
    profiles=[provider,*alternatives]
    limits=settings['limits'];binding={'primary':_provider_binding(provider),'fallbacks':[_provider_binding(p) for p in alternatives]};result={**result,'review_binding':binding}
    budget_scope=fingerprint({k:state[k] for k in ('scope','permission','selection_version','normalization_version')})
    try:budget=CoverageBudget(root/'requests.sqlite3',job_id=job['session_id'],
            budget_identity=state['semantic_budget_identity'],parent_attempts=job['attempts'],
            max_requests=limits['model_requests'],max_tokens=limits['model_tokens'],scope_identity=budget_scope)
    except ValueError as error:
        if str(error) not in {'budget_identity_changed','budget_scope_changed'}:raise
        try:budget=CoverageBudget.continue_generation(root/'requests.sqlite3',job_id=job['session_id'],scope_identity=budget_scope,parent_attempts=job['attempts'])
        except ValueError:
            return {**result,'status':'budget_paused','reason':'parent_scope_changed_no_new_budget','model_calls':0,
                'budget':CoverageBudget.existing_status(root/'requests.sqlite3',job['session_id'])}
    budget.recover_orphaned_requests()
    def source_current():return (store.validate_snapshot(state['snapshot_id'],permission_getter())['valid'] and scope_getter()==state['scope']
        and (parent_lease_valid is None or parent_lease_valid()))
    def reserve(stage,payload,estimate):
        sha=fingerprint(payload)
        budget.ensure_request_available(stage,sha,estimate)
        if not source_current():raise ValueError('source_or_permission_changed')
        if authorize_request is not None:authorize_request()
        if not source_current():raise ValueError('source_or_permission_changed')
        return budget.reserve_request(stage,sha,estimate)
    local=[];global_parts=[];calls=0;reused_count=0;failure=None;coverage=None
    def saved(payload):
        path=root/'reviews'/(fingerprint(payload)+'.json')
        if path.is_symlink():raise ValueError('coverage_cache_invalid')
        try:
            with path.open('rb') as f:raw=f.read(4*1024*1024+1)
            if len(raw)>4*1024*1024:return None
            return json.loads(raw)
        except (OSError,ValueError):return None
    def execute(stage,build,restore,invoke,accepted_status):
        nonlocal calls,reused_count
        for index,profile in enumerate(profiles):
            if getattr(profile,'requires_parent_lease',False) and authorize_request is None:raise ValueError('parent_lease_required')
            selection={'chain':binding,'selected':_provider_binding(profile)}
            payload,context=build(selection)
            prior=saved(payload)
            reused=restore(prior,context) if prior else None
            if reused is not None:
                reused_count+=1;return reused
            prior_proof=bool(prior and prior.get('request_sha256')==fingerprint(payload)
                and budget.receipt_matches(prior.get('reservation_id'),stage,fingerprint(payload),prior.get('response_sha256')))
            if prior_proof and prior.get('status')=='rejected':raise ValueError(stage+'_review_not_accepted')
            if prior_proof and prior.get('status')=='unavailable':
                if index<len(profiles)-1:continue
                # Explicit new run of a failed transport, still charged against
                # the original ceiling. This is not a semantic-veto retry.
                selection={**selection,'transport_retry_of':prior['reservation_id']}
                payload,context=build(selection)
                retried=saved(payload)
                reused=restore(retried,context) if retried else None
                if reused is not None:reused_count+=1;return reused
            reservation=reserve(stage,payload,len(canonical(payload))+limits['partition_output_tokens'])
            if not source_current():raise ValueError('source_or_permission_changed')
            receipt=invoke(profile,reservation,context);calls+=1
            _write(root/'reviews'/(fingerprint(payload)+'.json'),dict(receipt))
            if receipt['status']=='unavailable':continue
            if receipt['status']!=accepted_status:raise ValueError(stage+'_review_not_accepted')
            return receipt
        raise ValueError('provider_failed')
    try:
        for part in plan['partitions']:
            def build_local(selection):
                candidate={'navigation_only':True,'review_binding':selection,'scope':state['scope'],'requirement_ids':[r['requirement_id'] for r in requirements['requirements'] if part['partition_id'] in r['partition_ids']]}
                return local_payload(part,candidate),candidate
            receipt=execute('local',build_local,lambda prior,candidate:restore_local_review(prior,part,candidate,budget),
                lambda profile,reservation,candidate:review_partition(part,candidate,profile,reservation,budget),'local_reviewed')
            local.append(receipt)
        ledger={'partition_plan':plan,'requirements':requirements,'local_reviews':local}
        from .scenario_intent_ledger import materialize_intents,navigation_projection
        intents=materialize_intents(state,plan,requirements,local)
        global_plan=plan_global_review(state,ledger,capacity=limits['partition_input_tokens'],provider_binding=binding)
        byid={r['requirement_id']:{**r,'local_findings':[i for i in intents if i['requirement_id']==r['requirement_id']]} for r in requirements['requirements']}
        for part in global_plan['parts']:
            receipt=execute('global',lambda selection:(global_payload(part,byid.__getitem__,plan=global_plan,request_binding=selection),selection),
                lambda prior,selection:restore_global_part(prior,part,byid.__getitem__,budget,plan=global_plan,request_binding=selection),
                lambda profile,reservation,selection:review_global_partition(part,byid.__getitem__,profile,reservation,budget,plan=global_plan,request_binding=selection),'global_part_reviewed')
            global_parts.append(receipt)
        coverage=validate_global_coverage(global_plan,global_parts,ledger)
        if coverage['status']=='accepted':
            if not source_current():raise ValueError('source_or_permission_changed')
            intents=materialize_intents(state,plan,requirements,local,coverage['requirement_states'])
            navigation=navigation_projection(intents)
            published=publish_segmented_navigation(state,{'summary':navigation['summary']},coverage,
                expected_generation=state['generation'],store=store,permission=permission_getter())
            published.update(navigation,intent_ledger=intents,review_binding=binding,scope=state['scope'],
                watermark=state['checkpoint'],partition_count=len(plan['partitions']),
                local_review_count=len(local),global_review_count=len(global_parts),budget=budget.status())
            _write(root/'navigation'/f"{job['session_id']}.json",published)
            _write(root/'navigation'/(state['snapshot_id']+'.json'),published)
            result={**result,'published':True,'status':'accepted','semantic_review_status':coverage['semantic_review_status']}
        else:failure='global_coverage_incomplete'
    except ValueError as error:
        allowed={'budget_paused','parent_attempts_exhausted','request_already_reserved','source_or_permission_changed',
            'local_review_not_accepted','global_review_not_accepted','reservation_input_underestimated','global_source_partition_capacity_exceeded',
            'parent_job_busy','parent_job_changed','parent_lease_expired','provider_failed','parent_lease_required'}
        failure=str(error) if str(error) in allowed else 'coverage_stage_rejected'
    if local:
        from .scenario_intent_ledger import materialize_intents
        _write(root/'review-ledger'/(state['snapshot_id']+'.json'),{'snapshot_id':state['snapshot_id'],
            'generation':state['generation'],'scope':state['scope'],'review_binding':binding,'coverage':dict(coverage) if coverage is not None else {},
            'intent_ledger':materialize_intents(state,plan,requirements,local,
                coverage['requirement_states'] if coverage is not None and coverage['status']=='accepted' else None),
            'semantic_scope':'local_only_not_global' if coverage is None or coverage['status']!='accepted' else 'declared_global_scope'})
    return {**result,'model_calls':calls,'reused_review_requests':reused_count,'budget':budget.status(),'reason':failure,
        'status':result['status'] if failure is None else ('budget_paused' if failure in {'budget_paused','parent_attempts_exhausted'} else 'partial')}
