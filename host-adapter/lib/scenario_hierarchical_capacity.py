"""Source-complete transport adaptation against the actual configured request."""
from .scenario_coverage_contract import canonical,fingerprint,hierarchical_protocol_fingerprint,contract
from .scenario_coverage_incremental import _provider_binding
from .scenario_coverage_partition import partition_snapshot,validate_partition
from .scenario_hierarchical_plan import plan_hierarchical_work
from .scenario_hierarchical_transport import semantic_windows,fits_request
from .scenario_hierarchical_review import build_review_request
from .scenario_hierarchical_host_planes import host_plane_registry


def review_binding(snapshot,provider):
    binding={k:snapshot[k] for k in ('snapshot_id','generation','scope','permission','selection_version','normalization_version')}
    binding.update(protocol='hierarchical_review.v1',protocol_fingerprint=hierarchical_protocol_fingerprint(),
        wire_contract=host_plane_registry()['schema'],
        provider=_provider_binding(provider) if provider is not None else None,
        provider_chain=[_provider_binding(p) for p in [provider,*getattr(provider,'fallback_providers',lambda:[])()]] if provider else [])
    return binding


def prepare_review_work(snapshot,limits,provider,partitions=None,binding=None):
    if provider is None:raise ValueError('ep_provider_configuration_unavailable')
    binding=review_binding(snapshot,provider) if binding is None else binding
    if partitions is None:
        raw_cap=contract()['review_protocols']['hierarchical_review.v1']['raw_source_window_bytes']
        partitions=partition_snapshot(snapshot,capacity=max(4,min(raw_cap,limits['partition_input_tokens']//3)),context_tokens=limits['context_tokens'],prefer_boundaries=True)
    prepared=prepare_review_windows(snapshot,partitions,binding,limits,provider)
    plan=plan_hierarchical_work(snapshot,prepared['plan'],{}, {'input_bound':limits['partition_input_tokens'],
        'output_bound':limits['partition_output_tokens'],'envelope_bytes':1800,'wire_input_sizes':prepared['wire_input_sizes']},limits)
    plan['transport_adaptation']=prepared['adaptation']
    plan['review_binding_fingerprint']=fingerprint(binding)
    if prepared['status']!='planned':plan['status']='capacity_paused'
    return {'binding':binding,'source_partitions':partitions,'partitions':prepared['plan'],'plan':plan}


def prepare_review_windows(snapshot,partitions,binding,limits,provider):
    if not validate_partition(partitions,snapshot)['complete']:raise ValueError('partition_coverage_invalid')
    if partitions.get('boundary_preference')!='structural_not_semantic':
        partitions=partition_snapshot(snapshot,capacity=partitions['capacity'],context_tokens=partitions['context_tokens'],prefer_boundaries=True)
    initial=partitions['capacity'];capacity=initial;context=partitions['context_tokens'];attempts=0;plan=partitions
    profiles=[provider,*getattr(provider,'fallback_providers',lambda:[])()]
    def request(part,profile):return build_review_request('extract',{**binding,'selected_provider':_provider_binding(profile)},{'partition':part},limits)
    raw_cap=contract()['review_protocols']['hierarchical_review.v1']['raw_source_window_bytes']
    def fits(part):return (sum(len(s['text'].encode()) for s in part['primary'])<=raw_cap
        and all(fits_request(request(part,p),p) for p in profiles))
    while True:
        attempts+=1
        windows=semantic_windows(snapshot,plan,limits,fits=fits)
        if not validate_partition(windows,snapshot)['complete']:raise ValueError('adaptive_source_coverage_invalid')
        sizes=[max(len(canonical(getattr(profile,'request_envelope',lambda r:r['model_request'])(request(p,profile)))) for profile in profiles) for p in windows['partitions']]
        complete=all(fits(p) for p in windows['partitions'])
        adaptation={'attempts':attempts,'initial_capacity':initial,'effective_capacity':capacity,
            'requested_context_bytes':partitions['context_tokens'],'effective_context_bytes':plan['context_tokens'],
            'max_extract_wire_bytes':max(sizes,default=0),'source_scope_reduced':False,
            'measurement':'full_configured_wire_bytes' if hasattr(provider,'request_envelope') else 'host_model_request_bytes'}
        if complete or capacity==4:
            return {'status':'planned' if complete else 'capacity_paused','plan':windows,
                'wire_input_sizes':sizes,'adaptation':adaptation}
        capacity=max(4,capacity//2)
        plan=partition_snapshot(snapshot,capacity=capacity,context_tokens=min(context,capacity//2),prefer_boundaries=True)
