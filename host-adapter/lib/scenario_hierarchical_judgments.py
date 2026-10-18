"""Separate faithful conversation attribution from identity and external truth."""
from copy import deepcopy
from .scenario_coverage_contract import contract


def normalize_judgments(result,stage):
    registry=contract()['review_protocols']['hierarchical_review.v1']
    if 'judgment_schema' not in result and 'review_axes' not in result:return None
    if result.get('judgment_schema')!=registry['judgment_schema']:raise ValueError('judgment_schema_invalid')
    if any(k in result for k in ('accept','intent_sufficient','conditions_preserved')):raise ValueError('conflicting_review_contracts')
    value=result.get('review_axes')
    if not isinstance(value,dict) or set(value)!={'attribution','scope','outcome'}:raise ValueError('review_axes_invalid')
    for axis,states in [('attribution',registry['attribution_states']),('scope',registry['scope_states'])]:
        row=value[axis]
        if (not isinstance(row,dict) or row.get('status') not in states or not isinstance(row.get('issues'),list)
                or any(not isinstance(i,str) or not i.strip() for i in row['issues'])):raise ValueError('review_axes_invalid')
        if row['status'] in {'defective','unresolved','needs_context'} and not row['issues']:raise ValueError('review_axes_missing_issue')
    attr=value['attribution']
    if type(attr.get('conditions_preserved')) is not bool:raise ValueError('review_axes_invalid')
    if attr['status']=='sufficient' and (attr['issues'] or attr['conditions_preserved'] is not True):raise ValueError('attribution_gap')
    if value['scope']['status']=='resolved' and value['scope']['issues']:raise ValueError('scope_axes_conflict')
    if not isinstance(value['outcome'],dict) or value['outcome'].get('status')!='not_verified':raise ValueError('external_outcome_unverified')
    requests=result.get('context_requests',[])
    if not isinstance(requests,list):raise ValueError('context_request_invalid')
    if stage in {'extract','leaf'} and 'needs_context' in {attr['status'],value['scope']['status']} and not requests:raise ValueError('context_request_missing')
    if attr['status']=='defective':raise ValueError('attribution_gap')
    return deepcopy(value)


def needs_context(receipt):
    if receipt.get('stage')=='extract' and receipt.get('status')=='proposed':
        return bool((receipt.get('result') or {}).get('context_requests'))
    axes=receipt.get('review_axes') or {}
    return any(axes.get(k,{}).get('status')=='needs_context' for k in ('attribution','scope'))


def attribution_reviewed(receipt):
    axes=receipt.get('review_axes')
    return receipt.get('status')=='reviewed' and (axes is None or axes['attribution']['status']=='sufficient')
