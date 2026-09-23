"""Truthful per-layer guidance receipts; no inference from a zero count."""
def guidance_receipt(controller,candidates,outputs,deferred_items=()):
    side=controller.get('guidance_sidecar') or {};layers={}
    facets={f.get('label') for f in controller.get('facets') or []}
    for kind,key in [('observation','observation'),('mental_model','mental_model'),('direct_policy','direct_policy')]:
        candidate_ids={r.get('id') for r in candidates if r.get('type')==kind and r.get('id')}
        output_ids={r.get('id') for r in outputs if r.get('type')==kind and r.get('id')}
        deferred_ids={r.get('id') for r in deferred_items if r.get('type')==kind and r.get('id')}
        request=side.get(key)
        detail=side.get('mental_models' if kind=='mental_model' else 'direct_policies' if kind=='direct_policy' else 'observations') or {}
        if kind=='direct_policy':request=side.get('enabled')
        executed=bool(detail.get('status')) or bool(candidate_ids) or ('stable_guidance_observations' in facets if kind=='observation' else False)
        failed=detail.get('status')=='failed'
        status='injected' if output_ids else 'execution_failed' if failed else 'deferred_by_transport_budget' if deferred_ids else 'checked_no_qualified_output' if executed else 'not_executed' if request else 'not_requested' if request is False else 'unknown'
        layers[kind]={'requested':request,'status':status,'candidate_count':len(candidate_ids),'output_count':len(output_ids),
                      'output_ids':sorted(output_ids),'deferred_count':len(deferred_ids),'deferred_ids':sorted(deferred_ids),'execution':detail}
    return {'schema':1,'memory_needs':controller.get('memory_needs') or {},'layers':layers,
            'meaning':'候选、是否实际检查、最终输出分开；0条不能证明该层没有适用内容。'}
