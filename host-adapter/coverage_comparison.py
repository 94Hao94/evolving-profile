"""Validate explicit human/Agent-reviewed three-way evidence, not model confidence."""
def _reviewed(side):
    return type(side.get('supported')) is bool and bool(side.get('reviewer')) and bool(side.get('witness'))

def evaluate(case):
    errors=[];rows=[]
    if case.get('holdout') and case.get('used_for_tuning'):errors.append('holdout_used_for_tuning')
    if not case.get('requirements'):errors.append('no_requirements')
    for requirement in case.get('requirements',[]):
        bank=requirement.get('independent_bank') or {};delivery=requirement.get('delivered') or {};context=requirement.get('context') or {}
        if not bank.get('source_ids'):state='baseline_incomplete'
        elif not _reviewed(bank) or not _reviewed(delivery):state='unreviewed'
        elif requirement.get('conflicts_with_current_prompt'):state='scope_conflict'
        elif bank['supported'] and not delivery['supported']:state='delivery_gap'
        elif delivery['supported'] and not bank['supported']:state='unsupported_delivery'
        elif requirement.get('required') and not bank['supported']:state='bank_gap_or_baseline_incomplete'
        elif not _reviewed(context):state='context_baseline_unreviewed'
        elif not _reviewed(requirement.get('answer') or {}):state='answer_use_unreviewed'
        elif requirement.get('required') and not requirement['answer']['supported']:state='answer_gap'
        else:state='reviewed_covered'
        rows.append({'id':requirement.get('id'),'state':state})
    return {'requirements':rows,'errors':errors,'passed':bool(rows) and not errors and all(r['state']=='reviewed_covered' for r in rows),
        'meaning':'Result validates declared review evidence structure and gaps, not semantic truth or exhaustive Bank coverage.'}
