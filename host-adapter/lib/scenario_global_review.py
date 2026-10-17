"""Exhaustive declared cross-partition plan, with explicit unreviewed edges."""
import hmac
import os

from .scenario_coverage_contract import canonical,fingerprint
from .scenario_coverage_review import DISPOSITIONS
from .scenario_coverage_contract import contract

_KEY=os.urandom(32)


class GlobalCoverage(dict):
    def __init__(self,value):
        super().__init__(value);self.seal=hmac.digest(_KEY,canonical(value),'sha256')


def valid_global_coverage(value):
    return isinstance(value,GlobalCoverage) and hmac.compare_digest(value.seal,hmac.digest(_KEY,canonical(dict(value)),'sha256'))


def plan_global_review(snapshot,ledger,*,capacity=6000,max_edges=100000,provider_binding=None):
    reqs=ledger['requirements']['requirements'];parts=[];edges=[];complete=True
    for i,a in enumerate(reqs):
        for b in reqs[i+1:]:
            if len(edges)>=max_edges:complete=False;break
            edge={'from':a['requirement_id'],'to':b['requirement_id']}
            edges.append({**edge,'edge_id':fingerprint([snapshot['snapshot_id'],edge])})
        if not complete:break
    req_by_id={r['requirement_id']:r for r in reqs}
    sizes={rid:len(req.get('text','').encode())+
           sum(len(a.get('text','').encode()) for a in req.get('assistant_context',[])) for rid,req in req_by_id.items()}
    output_limit=contract()['defaults']['partition_output_tokens']
    def response_bytes(ids,eids):
        # Conservative UTF-8 bytes, not a claim about the Provider tokenizer.
        return len(canonical({'accept':True,'issues':[],'relations':[],'read_requirement_ids':ids,'reviewed_edge_ids':eids,
            'requirement_states':[{'requirement_id':rid,'status':'non_substantive'} for rid in ids]}))+256
    # Transport batching only: every declared pair still needs an explicit
    # reviewed edge. Shared full source is sent once per bounded batch, not
    # once per pair. Do not infer that unlisted pairs were checked.
    covered=set()
    for edge in edges:
        ids=[edge['from'],edge['to']]
        merged=list(dict.fromkeys([*(parts[-1]['requirement_ids'] if parts else []),*ids]))
        if parts and sum(sizes[rid] for rid in merged)<=capacity and response_bytes(merged,[*parts[-1]['edge_ids'],edge['edge_id']])<=output_limit:
            parts[-1]['requirement_ids']=merged
            parts[-1]['edge_ids'].append(edge['edge_id'])
        else:parts.append({'kind':'boundary','requirement_ids':ids,'edge_ids':[edge['edge_id']]})
        covered.update(ids)
    # With no edges (or an edge planning cap), singleton requirements still
    # have an explicit full-source review obligation.
    for req in reqs:
        rid=req['requirement_id']
        if rid in covered:continue
        merged=list(dict.fromkeys([*(parts[-1]['requirement_ids'] if parts else []),rid]))
        if parts and sum(sizes[item] for item in merged)<=capacity and response_bytes(merged,parts[-1]['edge_ids'])<=output_limit:parts[-1]['requirement_ids']=merged
        else:parts.append({'kind':'requirement','requirement_ids':[rid],'edge_ids':[]})
    for part in parts:part['part_id']=fingerprint([snapshot['snapshot_id'],part])
    for part in parts:
        source_bytes=sum(sizes[rid] for rid in part['requirement_ids'])
        part['source_input_bytes']=source_bytes
        part['requires_additional_source_partition']=source_bytes>capacity
        part['required_response_bytes']=response_bytes(part['requirement_ids'],part['edge_ids'])
        part['requires_smaller_response']=part['required_response_bytes']>output_limit
    if any(p['requires_additional_source_partition'] for p in parts):complete=False
    if any(p['requires_smaller_response'] for p in parts):complete=False
    from .scenario_coverage_partition import validate_partition
    structural=validate_partition(ledger['partition_plan'],snapshot)['complete'] if 'units' in snapshot else False
    body={'snapshot_id':snapshot['snapshot_id'],'generation':snapshot['generation'],'parts':parts,
        'required_edges':edges,'ledger_sha256':fingerprint(ledger),'plan_complete':complete,
        'reason':None if complete else ('global_source_partition_capacity_exceeded' if any(p['requires_additional_source_partition'] for p in parts) else 'global_plan_edge_limit'),'capacity':capacity,'structural_complete':structural,
        'semantic_claim':'automated_declared_scope_review_not_absolute_completeness',
        'provider_binding':provider_binding,'scope':snapshot.get('scope'),
        'transport_packing':'global-bounded-shared-context.v1'}
    return {**body,'plan_id':fingerprint(body)}


def validate_relation(relation,requirements):
    byid={r['requirement_id']:r for r in requirements}
    if not isinstance(relation,dict):return False
    a,b=byid.get(relation.get('from')),byid.get(relation.get('to'))
    if not a or not b or a['snapshot_id']!=b['snapshot_id']:return False
    if relation.get('type')=='supersedes':
        return (a.get('role')=='user' and b.get('role')=='user' and a.get('sequence',-1)>b.get('sequence',-1)
            and relation.get('evidence_kind')=='explicit_user_correction' and isinstance(relation.get('evidence_quote'),str)
            and bool(relation['evidence_quote']) and relation['evidence_quote'] in a['text'])
    return relation.get('type')=='conflicts' and a['requirement_id']!=b['requirement_id']


def global_payload(plan_part,source_access,*,plan,request_binding=None):
    if plan_part not in plan['parts']:raise ValueError('global_plan_part_unknown')
    if plan_part.get('requires_additional_source_partition'):raise ValueError('global_source_partition_capacity_exceeded')
    if plan_part.get('requires_smaller_response'):raise ValueError('global_response_capacity_exceeded')
    reqs=[source_access(rid) for rid in plan_part['requirement_ids']]
    if any(r.get('snapshot_id')!=plan['snapshot_id'] or r.get('requirement_id')!=rid for r,rid in zip(reqs,plan_part['requirement_ids'])):
        raise ValueError('global_source_changed')
    return {'protocol':'segment-global-review.v1','plan_id':plan['plan_id'],'part':plan_part,'requirements':reqs,
        'provider_binding':plan.get('provider_binding'),'request_binding':request_binding,'scope':plan.get('scope'),
        'response_schema':{'type':'object','required':['accept','read_requirement_ids','reviewed_edge_ids','requirement_states','relations','issues'],
            'properties':{'accept':{'type':'boolean'},'issues':{'type':'array'},
                'read_requirement_ids':{'type':'array','items':{'enum':plan_part['requirement_ids']},'minItems':len(reqs),'maxItems':len(reqs),'uniqueItems':True},
                'reviewed_edge_ids':{'type':'array','items':({'enum':plan_part['edge_ids']} if plan_part['edge_ids'] else {'type':'string'}),'minItems':len(plan_part['edge_ids']),'maxItems':len(plan_part['edge_ids']),'uniqueItems':True},
                'requirement_states':{'type':'array','items':{'type':'object','required':['requirement_id','status'],
                    'properties':{'requirement_id':{'enum':plan_part['requirement_ids']},'status':{'enum':sorted(DISPOSITIONS)}}}},
                'relations':{'type':'array','items':{'type':'object','required':['type','from','to'],
                    'properties':{'type':{'enum':['supersedes','conflicts']},'from':{'enum':plan_part['requirement_ids']},'to':{'enum':plan_part['requirement_ids']},
                        'evidence_kind':{'enum':['explicit_user_correction']},'evidence_quote':{'type':'string'}}}}}},
        'instruction':'Return one JSON object conforming to response_schema, with ALL six required top-level fields. Read all complete source requirements and explicitly list ALL supplied edge IDs, even when no conflict is found. States MUST use the declared enum; do not invent resolved/current/completed. answered means an assistant response exists, not that an external outcome was verified. Check remote corrections and task/phase/project boundaries. A supersedes relation requires later explicit USER evidence_kind=explicit_user_correction and an exact evidence_quote; from=later user requirement, to=older one. Unknown scope stays unresolved. Do not infer same project from cwd/institution. Do not claim external fact verification.'}


def review_global_partition(plan_part,source_access,provider,reservation,budget,*,plan,request_binding=None):
    if reservation is None:raise ValueError('reservation_required')
    payload=global_payload(plan_part,source_access,plan=plan,request_binding=request_binding);reqs=payload['requirements']
    if reservation.get('stage')!='global' or reservation.get('input_fingerprint')!=fingerprint(payload):
        raise ValueError('reservation_input_mismatch')
    if len(canonical(payload))>reservation.get('estimate',0):raise ValueError('reservation_input_underestimated')
    budget.dispatch(reservation)
    base={'plan_id':plan['plan_id'],'part_id':plan_part['part_id'],'snapshot_id':plan['snapshot_id'],
        'request_sha256':fingerprint(payload),'reservation_id':reservation['id'],'external_fact_verified':False}
    try:response=provider(payload);sha=fingerprint(response)
    except Exception:
        budget.settle_request(reservation,None,response_fingerprint=None)
        return {**base,'status':'unavailable','response_sha256':None}
    budget.settle_request(reservation,response.get('usage') if isinstance(response,dict) else None,response_fingerprint=sha)
    result=response.get('result') if isinstance(response,dict) else None
    valid=validate_global_part_result(plan_part,reqs,result)
    value={**base,'status':'global_part_reviewed' if valid else 'rejected','response_sha256':sha,'result':result,'provider_response':response}
    return GlobalCoverage(value)


def validate_global_part_result(plan_part,reqs,result):
    valid=isinstance(result,dict) and result.get('accept') is True and result.get('issues')==[]
    if valid:
        read=result.get('read_requirement_ids');covered=result.get('reviewed_edge_ids');states=result.get('requirement_states')
        valid=(isinstance(read,list) and len(read)==len(reqs) and set(read)==set(plan_part['requirement_ids'])
            and isinstance(covered,list) and len(covered)==len(plan_part['edge_ids']) and set(covered)==set(plan_part['edge_ids'])
            and isinstance(states,list) and len(states)==len(reqs)
            and {r.get('requirement_id') for r in states if isinstance(r,dict)}==set(read)
            and all(isinstance(r,dict) and r.get('status') in DISPOSITIONS for r in states)
            and isinstance(result.get('relations'),list) and all(validate_relation(r,reqs) for r in result['relations']))
    return valid


def restore_global_part(value,plan_part,source_access,budget,*,plan,request_binding=None):
    try:
        payload=global_payload(plan_part,source_access,plan=plan,request_binding=request_binding);response=value['provider_response'];sha=fingerprint(payload)
        valid=(value['status']=='global_part_reviewed' and value['plan_id']==plan['plan_id']
            and value['part_id']==plan_part['part_id'] and value['snapshot_id']==plan['snapshot_id']
            and value['request_sha256']==sha and value['response_sha256']==fingerprint(response)
            and value['result']==response['result'] and validate_global_part_result(plan_part,payload['requirements'],value['result'])
            and budget.receipt_matches(value['reservation_id'],'global',sha,value['response_sha256']))
        return GlobalCoverage(value) if valid else None
    except (KeyError,ValueError,TypeError):return None


def validate_global_coverage(plan,parts,ledger):
    missing=[];byid={};conflicts=[];states={};relations=[];state_values={}
    for part in parts:
        if not valid_global_coverage(part) or part.get('plan_id')!=plan['plan_id']:continue
        if part['status']=='global_part_reviewed':byid[part['part_id']]=part
    for expected in plan['parts']:
        receipt=byid.get(expected['part_id'])
        if not receipt:missing.append(expected['part_id']);continue
        for row in receipt['result']['requirement_states']:
            state_values.setdefault(row['requirement_id'],set()).add(row['status'])
        relations.extend(receipt['result']['relations'])
    local=ledger.get('local_reviews',[])
    expected_local={p['partition_id'] for p in ledger['partition_plan']['partitions']}
    # Local receipts must come from the actual review function, not model copies.
    from .scenario_coverage_review import valid_local_review
    expected_partitions={p['partition_id']:p for p in ledger['partition_plan']['partitions']}
    actual_local={r['partition_id'] for r in local if valid_local_review(r) and r.get('status')=='local_reviewed'
        and r['partition_id'] in expected_partitions and r.get('partition_sha256')==fingerprint(expected_partitions[r['partition_id']])}
    local_missing=sorted(expected_local-actual_local)
    from .scenario_coverage_partition import build_requirement_catalog
    try:catalog_matches=fingerprint(ledger['requirements'])==fingerprint(build_requirement_catalog(ledger['partition_plan']))
    except (KeyError,ValueError,TypeError):catalog_matches=False
    changed=(plan['ledger_sha256']!=fingerprint(ledger) or not catalog_matches
        or plan['plan_id']!=fingerprint({k:v for k,v in plan.items() if k!='plan_id'}))
    reqs=ledger['requirements']['requirements']
    for relation in relations:
        if relation.get('type')=='conflicts':conflicts.extend([relation['from'],relation['to']])
    superseded={r['to'] for r in relations if r.get('type')=='supersedes'}
    for rid,values in state_values.items():
        if rid in superseded and values<={'covered','answered','superseded'}:states[rid]='superseded'
        elif len(values)==1:states[rid]=next(iter(values))
        else:conflicts.append(rid);states[rid]='unresolved'
    spans_to_req={span:row['requirement_id'] for row in reqs for span in row.get('spans',[])}
    for review in local:
        if not valid_local_review(review) or review.get('status')!='local_reviewed':continue
        for mapping in review['result']['intent_mappings']:
            rid=spans_to_req.get(mapping['span_id'])
            if mapping['disposition']=='omitted' and states.get(rid) not in {'omitted','unresolved'}:
                conflicts.append(rid)
    for req in reqs:
        if states.get(req['requirement_id'])=='omitted':conflicts.append(req['requirement_id'])
        if states.get(req['requirement_id'])=='superseded' and not any(r.get('type')=='supersedes' and r.get('to')==req['requirement_id'] for r in relations):
            conflicts.append(req['requirement_id'])
    accepted=plan['plan_complete'] and plan.get('structural_complete') is True and not missing and not local_missing and not changed and not conflicts
    value={'schema':'segment_coverage.v1','snapshot_id':plan['snapshot_id'],'generation':plan['generation'],
        'plan_id':plan['plan_id'],'ledger_sha256':plan['ledger_sha256'],
        'status':'accepted' if accepted else ('conflicted' if conflicts else 'partial'),
        'missing_part_ids':missing,'missing_local_partition_ids':local_missing,'conflicts':list(dict.fromkeys(conflicts)),
        'requirement_states':states,'relations':relations,'source_manifest_complete':plan.get('structural_complete') is True,
        'semantic_review_status':'automated_declared_scope_accepted' if accepted else 'incomplete',
        'overall_complete':bool(accepted and all(s not in {'unresolved','omitted'} for s in states.values())),
        'external_fact_verified':False,'source_readback':False,'task_outcome_verified':False}
    return GlobalCoverage(value)
