"""Conservative preflight, not a promise of semantic success or linear cost."""
from .scenario_coverage_contract import canonical,fingerprint


def plan_hierarchical_work(snapshot, partitions, capsule_manifest, capability, limits):
    parts=partitions.get('partitions',[]);count=len(parts)
    inp=capability.get('input_bound',limits['partition_input_tokens'])
    out=capability.get('output_bound',limits['partition_output_tokens'])
    envelope=capability.get('envelope_bytes',len(canonical({'binding':snapshot.get('scope'),
        'instruction':'untrusted source; preserve source, intent and conditions','response_schema':{}}))+1024)
    values=[inp,out,envelope,limits['partition_output_tokens']]
    if any(type(n) is not int or n<0 for n in values):raise ValueError('hierarchical_capacity_invalid')
    source_sizes=[len(canonical(p)) for p in parts]
    wire=capability.get('wire_input_sizes')
    if wire is not None and (not isinstance(wire,list) or len(wire)!=count or any(type(n) is not int or n<0 for n in wire)):
        raise ValueError('hierarchical_capacity_invalid')
    too_large=(any(n>inp for n in wire) if wire is not None else any(n+envelope>inp for n in source_sizes)) or limits['partition_output_tokens']>out or inp<=envelope
    nodes=[];children=[p.get('partition_id',f'leaf-{i}') for i,p in enumerate(parts)]
    # A binary merge is a conservative topology, not a semantic grouping rule.
    while len(children)>1:
        parents=[]
        for i in range(0,len(children),2):
            group=children[i:i+2]
            if len(group)==1:parents.append(group[0]);continue
            key=fingerprint(['merge',group]);nodes.append({'node_id':key,'children':group});parents.append(key)
        children=parents
    if count==1:nodes=[{'node_id':fingerprint(['root',children]),'children':children}]
    return {'status':'capacity_paused' if too_large else 'planned','leaf_count':count,'merge_nodes':nodes,
        'minimum_requests':2*count+len(nodes),'exact_total_requests':None,'readback_requests':'depends_on_discovered_obligations',
        'counting':'conservative_utf8_bytes','input_bound':inp,'output_bound':out,'envelope_bytes':envelope,
        'input_measurement':'full_configured_wire_bytes' if wire is not None else 'host_partition_bytes_plus_envelope',
        'mandatory_output_preflight':'reserve_full_configured_output; unknown atom count may still require paging',
        'cross_scope_exhaustiveness':'not_exhaustive','overall_complete':False}
