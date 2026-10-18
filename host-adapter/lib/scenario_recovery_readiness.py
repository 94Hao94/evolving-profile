"""Read-only recovery advice. Never grants a retry or resets spent attempts."""
from .scenario_coverage_contract import contract


def recovery_readiness(job):
    attempts=job.get('attempts');maximum=contract()['defaults']['parent_max_attempts']
    valid=type(attempts) is int and attempts>=0
    remaining=max(0,maximum-attempts) if valid else None
    status,code=job.get('status'),str(job.get('error_code') or '')
    automatic=False
    if status=='protected':action='preserve_protection'
    elif not valid:action='inspect_unknown_budget'
    elif status=='complete':action='none'
    elif 'source_empty' in code or 'no_user_messages' in code:action='wait_for_source'
    elif remaining==0:action='new_authorization_required'
    elif 'budget_exceeded' in code or 'over_budget' in code:action='segmented_review_required'
    elif 'revision' in code or 'source_changed' in code:action='revalidate_source_before_retry'
    elif status=='retrying' and code in {'scenario_provider_unavailable','provider_unavailable'}:
        action='existing_bounded_transport_retry';automatic=True
    else:action='inspect_rejected_result'
    return {'session_id':job.get('session_id'),'status':status,'error_code':code or None,
            'original_attempts':attempts if valid else None,'remaining_original_attempts':remaining,
            'action':action,'automatic_retry_allowed':automatic,'attempts_reset':False,'summary_accepted':False}
