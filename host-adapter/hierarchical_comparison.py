"""Assertion-level evaluation, never converts missing reviews into success."""
from coverage_comparison import evaluate as evaluate_delivery
from lib.scenario_coverage_contract import fingerprint


def evaluate_hierarchical_case(case):
    case=case if isinstance(case,dict) else {};errors=[]
    if case.get('holdout') and case.get('used_for_tuning'):errors.append('holdout_used_for_tuning')
    requirements=case.get('requirements');requirements=requirements if isinstance(requirements,list) else []
    if not requirements:errors.append('no_independent_requirements')
    reviewed=[];missed=[];misused=[]
    for row in requirements:
        if not isinstance(row,dict):errors.append('invalid_requirement');continue
        reference=row.get('reference',{})
        if (not isinstance(reference,dict) or reference.get('independent') is not True or not reference.get('reviewer')
                or not reference.get('witness') or not reference.get('source_ids')):
            errors.append('reference_unreviewed');continue
        found=row.get('semantic_review')
        if not isinstance(found,dict) or type(found.get('preserved')) is not bool or not found.get('witness'):
            errors.append('intent_not_compared');continue
        reviewed.append(row.get('id'))
        if found['preserved'] is False:missed.append(row.get('id'))
        if found.get('scope_correct') is not True:misused.append(row.get('id'))
    cov=case.get('coverage');cov=cov if isinstance(cov,dict) else {}
    semantics=(bool(requirements) and len(reviewed)==len(requirements) and not errors and not missed and not misused
        and case.get('source_evidence_fresh') is True and case.get('failure') is None
        and case.get('status')=='scope_reviewed' and case.get('reason') is None
        and cov.get('coverage_contract')=='hierarchical_review.v1' and cov.get('target_complete') is True
        and cov.get('attribution_review')=='complete' and cov.get('scope_review')=='resolved'
        and cov.get('scope_axes_complete') is True
        and all(cov.get(k)=='complete' for k in ('source_coverage','intent_review','obligation_review','discovery_procedure_coverage'))
        and cov.get('cross_scope_exhaustiveness')=='not_exhaustive' and cov.get('unresolved_count')==0)
    # This is separate evidence. A producer model saying its atoms are good
    # cannot also assert that a host received/used them in an actual answer.
    answer_case=case.get('answer_comparison')
    benefit='not_measured';delivery=None
    if isinstance(answer_case,dict):
        delivery=evaluate_delivery(answer_case)
        if delivery['passed'] and {r.get('id') for r in answer_case.get('requirements',[])}==set(reviewed) and reviewed:
            benefit='measured'
    return {'case_id':case.get('case_id'),'semantic_ready':bool(semantics),'answer_benefit':benefit,
        'requirements_total':len(requirements),'requirements_reviewed':len(reviewed),
        'omitted_ids':missed,'scope_misuse_ids':misused,'errors':errors,'delivery_comparison':delivery,
        'external_fact_verified':False,'meaning':'Reviewed assertion evidence within the frozen case, not exhaustive relations or an accuracy guarantee.'}


def evaluate_manifest(evaluation,current_protocol):
    failed={'semantic_ready':False,'answer_benefit_measured':False,'case_count':0}
    try:
        if not isinstance(evaluation,dict) or not current_protocol or evaluation.get('protocol_fingerprint')!=current_protocol:return failed
        manifest=evaluation['case_manifest'];cases=evaluation['cases']
        if (not isinstance(manifest,list) or not manifest or not isinstance(cases,list)
                or evaluation.get('case_manifest_sha256')!=fingerprint(manifest)):return failed
        ids=[r['case_id'] for r in manifest];actual=[c['case_id'] for c in cases]
        if (any(not isinstance(i,str) for i in ids+actual) or len(set(ids))!=len(ids)
                or sorted(ids)!=sorted(actual)):return failed
        for ref in manifest:
            case=next(c for c in cases if c['case_id']==ref['case_id'])
            if (case.get('snapshot_id')!=ref['snapshot_id'] or case.get('validated_protocol_fingerprint')!=current_protocol
                    or fingerprint(case.get('requirements'))!=ref['requirements_sha256']):return failed
        rows=[evaluate_hierarchical_case(c) for c in cases]
        return {'semantic_ready':all(r['semantic_ready'] for r in rows),
            'answer_benefit_measured':all(r['answer_benefit']=='measured' for r in rows),'case_count':len(rows)}
    except (KeyError,ValueError,TypeError,StopIteration):return failed
