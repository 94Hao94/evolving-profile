"""Semantic windows and capsule-backed bounded merge pages, not top-k pruning."""
from copy import deepcopy
from .scenario_coverage_contract import canonical,fingerprint,contract
from .scenario_evidence_capsule import restore_capsules
from .scenario_hierarchical_review import build_review_request,InputCapacityExceeded


def semantic_windows(snapshot,plan,limits,*,fits=None):
    out=deepcopy(plan);parts=[]
    for part in plan['partitions']:
        if (parts and parts[-1]['primary'] and part['primary']
                and parts[-1]['primary'][-1]['unit_id']==part['primary'][0]['unit_id']):
            combined=[*parts[-1]['primary'],*part['primary']]
            candidate={**deepcopy(parts[-1]),'primary':deepcopy(combined),
                'partition_id':fingerprint([snapshot['snapshot_id'],combined]),'semantic_window':True}
            # Join transport fragments only while a full bounded semantic
            # window remains possible; never infer a task from punctuation.
            if len(canonical(combined))+1800<=limits['partition_input_tokens'] and (fits is None or fits(candidate)):
                parts[-1]=candidate
                continue
        parts.append(deepcopy(part))
    out['partitions']=parts;out['semantic_input_bound']=limits['partition_input_tokens']
    return out


def semantic_descriptor(item):
    keys=('atom_id','kind','authority','action','claim','conditions','negation','exceptions',
        'object_hypotheses','time','local_state','reason','scope_review_status')
    value={k:deepcopy(item[k]) for k in keys if k in item}
    if item.get('authority') in {'assistant_report','assistant_suggestion'} and not value.get('claim'):
        value['claim']=item['source_quote']
    value.update(evidence_sha256=fingerprint(item),source_ref_count=len(item.get('source_refs',[])),
        source_order=[r.get('sequence') for r in item.get('source_refs',[])],external_fact_verified=False)
    return value


def capsule_rows(capsule):
    value=restore_capsules(capsule)
    return {r['atom_id']:(kind,semantic_descriptor(r)) for kind,rows in value.items() for r in rows}


def fits_request(request,provider):
    envelope=getattr(provider,'request_envelope',lambda r:r['model_request'])(request)
    minimum_output={'judgment_schema':contract()['review_protocols']['hierarchical_review.v1']['judgment_schema'],
        'accepted_scope':'source_attribution_and_intent_only','read_ids':[r['id'] for r in request['catalog']],
        'review_axes':{'attribution':{'status':'sufficient','conditions_preserved':True,'issues':[]},
            'scope':{'status':'resolved','issues':[]},'outcome':{'status':'not_verified'}},
        'assistant_reports_are_unverified':True,'discovery_complete':True,'obligations':[],'object_links':[]}
    return (len(canonical(envelope))<=request['limits']['partition_input_tokens']
        and len(canonical(minimum_output))<=request['limits']['partition_output_tokens'])


def merge_pages(binding,node,ids,capsule,obligations,limits,provider,*,source_reader=None,prior_states=()):
    rows=capsule_rows(capsule);pages=[];current=[]
    def make(group,index):
        task_id=fingerprint(['merge-page',node['node_id'],index,group,capsule['manifest_sha256']])
        inputs={'task_id':task_id,'capsule_manifest_sha256':capsule['manifest_sha256'],
            'atoms':[rows[i][1] for i in group if rows[i][0]=='atoms'],
            'residuals':[rows[i][1] for i in group if rows[i][0]=='residuals'],
            'assistant_claims':[rows[i][1] for i in group if rows[i][0]=='assistant_claims'],
            'boundaries':[node],'obligations':[o for o in obligations if set(o['atom_ids'])&set(group)],
            'prior_states':deepcopy(list(prior_states))}
        if source_reader is not None:inputs['source_pages']=source_reader(group)
        return inputs,build_review_request('merge',binding,inputs,limits)
    for identity in ids:
        trial,request=make([*current,identity],len(pages))
        if current and not fits_request(request,provider):
            pages.append(make(current,len(pages))[0]);current=[]
        current.append(identity)
        request=make(current,len(pages))[1]
        if not fits_request(request,provider):
            envelope=getattr(provider,'request_envelope',lambda r:r['model_request'])(request)
            error=InputCapacityExceeded(request,len(canonical(envelope)))
            # No page from this invocation has reached an executor yet.
            # Include earlier locally planned pages and the unvisited suffix.
            error.unprocessed_record_ids=list(ids)
            raise error
    if current or not pages:pages.append(make(current,len(pages))[0])
    actual=[r['atom_id'] for p in pages for key in ('atoms','residuals','assistant_claims') for r in p[key]]
    if sorted(actual)!=sorted(ids) or len(actual)!=len(set(actual)):raise ValueError('capsule_ownership_incomplete')
    return pages
