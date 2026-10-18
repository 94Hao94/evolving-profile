"""Lossless decomposition after authenticated output truncation, never a veto retry."""
from copy import deepcopy
from .scenario_coverage_contract import contract,fingerprint
from .scenario_coverage_partition import _selected,_span


class OutputTruncated(ValueError):
    def __init__(self,receipt):
        super().__init__('capacity_paused');self.receipt=receipt


def output_truncated(receipt,stage):
    return (stage=='extract' and receipt.get('status')=='unavailable'
        and receipt.get('reason')=='provider_capacity_failed'
        and receipt.get('stage')=='extract' and receipt.get('result') is None
        and receipt.get('response_sha256')==fingerprint(receipt.get('provider_response'))
        and (receipt.get('provider_response') or {}).get('provider_failure')=='coverage_response_incomplete')


def split_failed_partition(snapshot,partition,*,depth,additional_windows):
    policy=contract()['review_protocols']['hierarchical_review.v1']['output_recovery']
    if depth>=policy['max_depth'] or additional_windows>=policy['max_additional_windows']:return None
    spans=partition['primary'];total=sum(len(s['text'].encode()) for s in spans)
    if total<2*policy['min_child_bytes']:return None
    # Cut nearest the byte midpoint on a Unicode boundary; semantic continuity
    # is not asserted. Normal leaf/context recovery must still judge meaning.
    target=total//2;used=0;left=[];right=[];selected={u['unit_id']:u for u in _selected(snapshot)[0]}
    for span in spans:
        if right:right.append(deepcopy(span));continue
        size=len(span['text'].encode())
        if used+size<=target:
            left.append(deepcopy(span));used+=size;continue
        cut=0
        for char in span['text']:
            if used+len(char.encode())>target:break
            cut+=1;used+=len(char.encode())
        unit=selected[span['unit_id']]
        if cut:left.append(_span(snapshot,unit,span['start'],span['start']+cut,span['text'][:cut]))
        if cut<len(span['text']):right.append(_span(snapshot,unit,span['start']+cut,span['end'],span['text'][cut:]))
    if any(sum(len(s['text'].encode()) for s in group)<policy['min_child_bytes'] for group in (left,right)):return None
    result=[]
    for primary in (left,right):
        result.append({**deepcopy(partition),'primary':primary,
            'partition_id':fingerprint([snapshot['snapshot_id'],primary]),
            'output_recovery_parent':partition['partition_id'],'output_recovery_depth':depth+1,
            'semantic_task_boundary':'unknown','reused_from_partition_id':None})
    return result
