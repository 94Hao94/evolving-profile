"""One charged invocation per request; bounded explicit transport recovery."""
import json
from pathlib import Path
from .scenario_coverage_contract import fingerprint
from .scenario_coverage_incremental import _write,_provider_binding
from .scenario_hierarchical_review import build_review_request,execute_review,restore_review,ReviewRejected,_validate
from .scenario_hierarchical_output_recovery import OutputTruncated,output_truncated


class ReviewExecutor:
    def __init__(self,binding,limits,folder,provider,budget,current,authorize_request,allow_profile):
        self.binding=binding;self.limits=limits;self.folder=Path(folder);self.budget=budget
        self.current=current;self.authorize=authorize_request
        self.profiles=[p for p in [provider,*getattr(provider,'fallback_providers',lambda:[])()] if allow_profile(p)]
        self.calls=0;self.cache_hits=0

    def _cached(self,request):
        path=self.folder/'reviews'/(fingerprint(request)+'.json')
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError('hierarchical_path_invalid')
        try:
            with path.open('rb') as f:raw=f.read(4*1024*1024+1)
            if len(raw)>4*1024*1024:return None,None
            value=json.loads(raw)
            return restore_review(value,request,self.budget),value
        except (OSError,ValueError):return None,None

    def _variants(self,stage,inputs):
        variants=[];capacity_failed=False
        for profile in self.profiles:
            selected={**self.binding,'selected_provider':_provider_binding(profile)}
            request=build_review_request(stage,selected,inputs,self.limits)
            hops=0
            while True:
                restored,raw=self._cached(request)
                if restored is not None:return restored,[]
                proof=(isinstance(raw,dict) and raw.get('request')==request
                    and raw.get('request_sha256')==fingerprint(request)
                    and self.budget.receipt_matches(raw.get('reservation_id'),'hierarchical_'+stage,
                        fingerprint(request),raw.get('response_sha256')))
                if raw is not None:
                    response=raw.get('provider_response') if isinstance(raw,dict) else None
                    response_sha=fingerprint(response) if response is not None else None
                    if not proof or raw.get('stage')!=stage or raw.get('response_sha256')!=response_sha:
                        raise ValueError('review_cache_invalid')
                    if raw.get('status')=='unavailable':
                        metadata=response if isinstance(response,dict) else {}
                        expected={'provider_capacity_failed','provider_failed'} if response is None else {
                            'provider_capacity_failed' if metadata.get('provider_failure') in {'coverage_response_incomplete','coverage_response_too_large'} else 'provider_failed'}
                        if raw.get('result') is not None or 'result' in metadata or raw.get('reason') not in expected:
                            raise ValueError('review_cache_invalid')
                    elif raw.get('status')!='rejected':raise ValueError('review_cache_invalid')
                if proof and output_truncated(raw,stage):raise OutputTruncated(raw)
                if proof and raw.get('status')=='rejected':
                    if raw.get('reason')=='source_or_permission_changed':raise ValueError('source_or_permission_changed')
                    response=raw.get('provider_response')
                    reason=_validate(request,response)
                    if (raw.get('response_sha256')!=fingerprint(response) or reason is None
                            or raw.get('result')!=(response.get('result') if isinstance(response,dict) else None)
                            or raw.get('reason')!=reason):raise ValueError('review_cache_invalid')
                    raise ReviewRejected(reason,raw)
                if proof and raw.get('status')=='unavailable':
                    if raw.get('reason')=='provider_capacity_failed':
                        capacity_failed=True;break
                    # Classify every retry hop through the same path; cached
                    # terminal failures must never become another paid retry.
                    request={**request,'transport_retry_of':raw['reservation_id']}
                    hops+=1
                    if hops>self.budget.status()['max_requests']:raise ValueError('budget_paused')
                    continue
                variants.append((profile,request));break
        if not variants and capacity_failed:raise ValueError('capacity_paused')
        return None,variants

    def __call__(self,stage,inputs):
        if not self.current():raise ValueError('source_or_permission_changed')
        restored,variants=self._variants(stage,inputs)
        if restored is not None:self.cache_hits+=1;return restored
        capacity_failed=False
        for profile,request in variants:
            out=execute_review(request,profile,self.budget,source_current=self.current,authorize_request=self.authorize)
            self.calls+=1
            _write(self.folder/'reviews'/(fingerprint(request)+'.json'),dict(out))
            if output_truncated(out,stage):raise OutputTruncated(out)
            if out['status'] in {'reviewed','needs_context'} or stage=='extract' and out['status']=='proposed':return out
            if out['status']!='unavailable':
                if out.get('reason')=='source_or_permission_changed':raise ValueError('source_or_permission_changed')
                raise ReviewRejected(out['reason'] or 'semantic_rejected',out)
            capacity_failed=capacity_failed or out.get('reason')=='provider_capacity_failed'
        raise ValueError('capacity_paused' if capacity_failed else 'provider_failed')
