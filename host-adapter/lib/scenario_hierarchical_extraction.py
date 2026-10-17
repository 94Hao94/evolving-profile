"""One charged structural re-selection; semantic vetoes are never retried here."""
from copy import deepcopy
from .scenario_coverage_contract import contract
from .scenario_hierarchical_review import expand_selected_aliases,ReviewRejected
from .scenario_hierarchical_selection import selection_enabled,identity_version_from_binding,decode_selection_proposal
from .scenario_hierarchical_host_planes import host_planes_enabled,source_roles_from_binding
from .scenario_intent_atoms import validate_atom_proposal


def mapping_feedback(snapshot,partition,proposal,errors,*,identity_version='source_offsets.v1',selection_request=None):
    policy=contract()['review_protocols']['hierarchical_review.v1']['extraction_repair']
    roles=source_roles_from_binding(selection_request['binding']) if selection_request is not None else ('user',)
    codes=list(errors);items=[];covered={s['span_id']:[] for s in partition['primary'] if s['role'] in roles and s['text']}
    inspected=0;partial=False
    if isinstance(proposal,dict):
        flat=selection_request is not None and host_planes_enabled(selection_request['binding'])
        for field in (('items',) if flat else ('atoms','residuals','assistant_claims')):
            rows=proposal.get(field)
            if not isinstance(rows,list):continue
            for index,item in enumerate(rows):
                if inspected>=policy['max_feedback_items']:partial=True;break
                inspected+=1
                single={k:[] for k in (('items',) if flat else ('atoms','residuals','assistant_claims'))};single[field]=[item]
                try:
                    if selection_request is not None:single=decode_selection_proposal(selection_request,single)
                    checked=validate_atom_proposal(snapshot,partition,single,identity_version=identity_version)
                except ValueError as error:checked={field:[],'errors':[str(error)]}
                local=[c for c in checked['errors'] if c!='intent_character_gap']
                codes.extend(local)
                if local:items.append({'field':field,'index':index,'errors':local})
                else:
                    for canonical_field in ('atoms','residuals','assistant_claims'):
                        for row in checked[canonical_field]:
                            for ref in row['source_refs']:
                                if ref['span_id'] in covered:covered[ref['span_id']].append((ref['start'],ref['end']))
    gaps=[]
    for span in partition['primary']:
        if span['span_id'] not in covered:continue
        at=0
        for start,end in sorted(covered[span['span_id']]):
            if start>at and not span['text'][at:start].isspace():gaps.append({'span_id':span['span_id'],'start':at,'end':start})
            at=max(at,end)
        if at<len(span['text']) and not span['text'][at:].isspace():gaps.append({'span_id':span['span_id'],'start':at,'end':len(span['text'])})
    for span in partition['primary']:
        if any(g['span_id']==span['span_id'] for g in gaps):codes.append('assistant_character_gap' if span['role']=='assistant' else 'intent_character_gap')
    return {'errors':list(dict.fromkeys(codes)),'item_errors':items,'uncovered_primary_ranges':gaps[:policy['max_feedback_items']],
        'empty_primary_spans':[{'span_id':s['span_id']} for s in partition['primary'] if not s['text']],
        'diagnostics_partial':partial or len(gaps)>policy['max_feedback_items'],
        'boundary':'host_mapping_feedback_not_semantic_acceptance; original source and model meanings unchanged'}


def extract_with_feedback(snapshot,partition,executor):
    policy=contract()['review_protocols']['hierarchical_review.v1']['extraction_repair'];repairs=[]
    version=identity_version_from_binding(getattr(executor,'binding',{}))
    roles=source_roles_from_binding(getattr(executor,'binding',{}))
    def invoke(inputs):
        try:return executor('extract',inputs)
        except ReviewRejected as error:
            if error.args[0] in {'selection_schema_invalid','proposal_fields'} and selection_enabled(getattr(executor,'binding',{})):return error.receipt
            raise
    def interpret(receipt):
        raw=receipt['result'].get('proposal',{})
        try:
            if receipt.get('status')=='rejected':raise ValueError(receipt['reason'])
            proposal=expand_selected_aliases(raw,receipt['request'])
        except ValueError as error:
            if not selection_enabled(receipt['request']['binding']):raise
            return raw,{'atoms':[],'residuals':[],'assistant_claims':[],'errors':[str(error)],'semantic_review_status':'not_reviewed','external_fact_verified':False}
        return proposal,validate_atom_proposal(snapshot,partition,proposal,identity_version=version,required_roles=roles)
    extraction=invoke({'partition':partition})
    proposal,checked=interpret(extraction)
    if checked['errors'] and policy['max_requests'] and set(checked['errors'])<=set(policy['mapping_errors']):
        raw_selection=selection_enabled(extraction['request']['binding'])
        feedback=mapping_feedback(snapshot,partition,extraction['result'].get('proposal',{}) if raw_selection else proposal,
            checked['errors'],identity_version=version,selection_request=extraction['request'] if raw_selection else None)
        feedback.update(previous_request_sha256=extraction['request_sha256'],previous_response_sha256=extraction['response_sha256'])
        record={'partition_id':partition['partition_id'],'initial_errors':checked['errors'],
            'initial_request_sha256':extraction['request_sha256'],'initial_response_sha256':extraction['response_sha256'],
            'feedback':feedback,'repair_attempts':1,'repair_model_calls':0,'status':'pending'}
        repairs.append(record);before=getattr(executor,'calls',0)
        try:
            # Full diagnostic detail stays in the durable receipt. The model
            # already receives the primary spans and trusted boundary text;
            # do not resend empty-span IDs or an English boundary disclaimer.
            wire_feedback={key:feedback[key] for key in ('errors','item_errors','uncovered_primary_ranges',
                'diagnostics_partial','previous_request_sha256','previous_response_sha256') if feedback.get(key)}
            extraction=invoke({'partition':partition,'validation_feedback':wire_feedback})
            proposal,checked=interpret(extraction)
            record.update(status='mapping_valid' if not checked['errors'] else 'mapping_invalid',
                final_errors=checked['errors'],final_request_sha256=extraction['request_sha256'])
        except ValueError as error:
            record.update(status='stopped',reason=str(error),repair_model_calls=getattr(executor,'calls',before)-before)
            error.format_repairs=repairs;raise
        record['repair_model_calls']=getattr(executor,'calls',before)-before
    if not checked['errors']:
        # Capsules already use the exact quoted report when the producer has
        # no separate claim. Show that SAME effective report to the independent
        # leaf, rather than asking it to judge only a generic action label.
        # This copies authenticated source literally; it does not add meaning,
        # change a supplied model claim or alter the producer response receipt.
        proposal=deepcopy(proposal)
        for row,source_row in zip(proposal['assistant_claims'],checked['assistant_claims']):
            if not row.get('claim'):row['claim']=source_row['source_quote']
        checked=validate_atom_proposal(snapshot,partition,proposal,identity_version=version,required_roles=roles)
    return extraction,proposal,checked,repairs
