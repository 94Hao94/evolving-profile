"""Local automated review. Declared coverage is checked, never globalized."""
from .scenario_coverage_contract import fingerprint,canonical
import hmac
import os

_KEY=os.urandom(32)


class LocalReview(dict):
    def __init__(self,value):
        super().__init__(value);self.seal=hmac.digest(_KEY,canonical(value),'sha256')


def valid_local_review(value):
    return isinstance(value,LocalReview) and hmac.compare_digest(value.seal,hmac.digest(_KEY,canonical(dict(value)),'sha256'))


KINDS={'request','constraint','correction','question','confirmation','unclassified_user_message'}
DISPOSITIONS={'covered','unresolved','omitted','superseded','answered','non_substantive'}


def validate_local_result(partition,result):
    spans=partition['primary'];byid={s['span_id']:s for s in spans}
    if not isinstance(result,dict) or type(result.get('accept')) is not bool:return 'malformed_review'
    if result['accept'] is not True:return 'semantic_rejected'
    read=result.get('read_span_ids')
    if not isinstance(read,list) or len(read)!=len(byid) or set(read)!=set(byid):return 'source_read_coverage_incomplete'
    if result.get('assistant_reports_are_unverified') is not True or result.get('issues')!=[]:return 'review_has_issues'
    mappings=result.get('intent_mappings')
    if not isinstance(mappings,list):return 'intent_coverage_incomplete'
    coverage={s['span_id']:[] for s in spans if s['role']=='user'}
    for m in mappings:
        if not isinstance(m,dict) or m.get('span_id') not in coverage:return 'intent_role_or_source_invalid'
        span=byid[m['span_id']];start,end=m.get('start'),m.get('end')
        if (type(start) is not int or type(end) is not int or not 0<=start<=end<=len(span['text'])
                or m.get('kind') not in KINDS or m.get('disposition') not in DISPOSITIONS):return 'intent_mapping_invalid'
        coverage[m['span_id']].append((start,end))
    for sid,intervals in coverage.items():
        if not byid[sid]['text']:continue
        cursor=0
        for start,end in sorted(intervals):
            if start>cursor:return 'intent_coverage_incomplete'
            cursor=max(cursor,end)
        if not intervals or cursor!=len(byid[sid]['text']):return 'intent_coverage_incomplete'
    return None


def local_payload(partition,candidate):
    return {'protocol':'segment-local-review.v1','partition':partition,'candidate':candidate,
        'response_schema':{'type':'object','required':['accept','read_span_ids','intent_mappings','issues','assistant_reports_are_unverified'],
            'properties':{'accept':{'type':'boolean'},'assistant_reports_are_unverified':{'const':True},'issues':{'type':'array'},
                'read_span_ids':{'type':'array','items':{'type':'string','enum':[s['span_id'] for s in partition['primary']]},
                    'minItems':len(partition['primary']),'maxItems':len(partition['primary']),'uniqueItems':True},
                'intent_mappings':{'type':'array','items':{'type':'object','required':['span_id','start','end','kind','disposition'],
                    'properties':{'span_id':{'type':'string'},'start':{'type':'integer','minimum':0},'end':{'type':'integer','minimum':0},
                        'kind':{'enum':sorted(KINDS)},'disposition':{'enum':sorted(DISPOSITIONS)}}}}}},
        'span_catalog':[{'span_id':s['span_id'],'role':s['role'],'text_length':len(s['text'])} for s in partition['primary']],
        'output_contract':{'accept':'top_level_boolean','read_span_ids':'top_level_array_all_primary_span_ids_including_empty',
            'issues':'top_level_array_empty_only_when_no_review_issues',
            'assistant_reports_are_unverified':'top_level_boolean_true',
            'intent_mappings':{'roles':['user'],'kind_enum':sorted(KINDS),'disposition_enum':sorted(DISPOSITIONS),
                'fields':['span_id','start','end','kind','disposition'],
                'offsets':'Python Unicode character offsets relative to each span text, not bytes or original message start. Cover every non-empty user character; empty metadata needs no intent. Never map assistant spans.'}},
        'instruction':'Return one JSON object conforming to response_schema and output_contract. ALL five top-level required fields are mandatory: accept, read_span_ids, intent_mappings, issues, assistant_reports_are_unverified. Copy every primary span_id into read_span_ids INCLUDING empty spans; intent_mappings is not a replacement for that list. Context_only is background, not required primary coverage. Preserve negation, role, scope and uncertainty. Use only the declared enum values. Assistant reports are context, not user intents or verified outcomes. Classify each user clause without dropping conditions. Do not claim global or external fact verification, and never invent acceptance to satisfy the format.'}


def restore_local_review(value,partition,candidate,budget):
    try:
        response=value['provider_response'];request_sha=fingerprint(local_payload(partition,candidate))
        valid=(value['status']=='local_reviewed' and value['request_sha256']==request_sha
            and value['partition_sha256']==fingerprint(partition) and value['candidate_sha256']==fingerprint(candidate)
            and value['snapshot_id']==partition['snapshot_id'] and value['partition_id']==partition['partition_id']
            and value['response_sha256']==fingerprint(response) and value['result']==response['result']
            and validate_local_result(partition,value['result']) is None
            and budget.receipt_matches(value['reservation_id'],'local',request_sha,value['response_sha256']))
        return LocalReview(value) if valid else None
    except (KeyError,ValueError,TypeError):return None


def review_partition(partition,candidate,provider,reservation,budget):
    if reservation is None:raise ValueError('reservation_required')
    payload=local_payload(partition,candidate)
    request_sha=fingerprint(payload)
    if reservation.get('stage')!='local' or reservation.get('input_fingerprint')!=request_sha:
        raise ValueError('reservation_input_mismatch')
    # Caller pre-reserves a conservative serialized input + configured output bound.
    if len(canonical(payload))>reservation.get('estimate',0):raise ValueError('reservation_input_underestimated')
    budget.dispatch(reservation)
    base={'snapshot_id':partition['snapshot_id'],'partition_id':partition['partition_id'],
        'candidate_sha256':fingerprint(candidate),'partition_sha256':fingerprint(partition),
        'request_sha256':request_sha,'overall_complete':False,'external_fact_verified':False,
        'reviewer_kind':'automated_provider_review','reservation_id':reservation['id']}
    try:
        response=provider(payload)
        response_sha=fingerprint(response)
    except Exception:
        budget.settle_request(reservation,None,response_fingerprint=None)
        return {**base,'status':'unavailable','reason':'provider_failed','response_sha256':None}
    receipt=budget.settle_request(reservation,response.get('usage') if isinstance(response,dict) else None,response_fingerprint=response_sha)
    result=response.get('result') if isinstance(response,dict) else None
    error=validate_local_result(partition,result)
    return LocalReview({**base,'status':'rejected' if error else 'local_reviewed','reason':error,'response_sha256':response_sha,
        'result':result,'usage':receipt,'provider_response':response})
