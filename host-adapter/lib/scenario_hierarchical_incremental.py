"""Scoped, resumable hierarchical orchestration; structural shadow by default."""
import hmac
import json
import os
from pathlib import Path
from .scenario_coverage_contract import canonical,fingerprint,hierarchical_protocol_fingerprint
from .scenario_coverage_budget import CoverageBudget
from .scenario_coverage_partition import partition_snapshot,validate_partition
from .scenario_coverage_store import CoverageStore
from .scenario_coverage_incremental import _write,_provider_binding
from .scenario_intent_atoms import validate_atom_proposal,bind_leaf_review
from .scenario_evidence_capsule import build_capsules
from .scenario_hierarchical_plan import plan_hierarchical_work
from .scenario_hierarchical_store import HierarchicalStore
from .scenario_hierarchical_review import build_review_request,execute_review,restore_review,expand_selected_aliases,logical_inputs
from .scenario_relation_obligations import build_discovery_tasks,validate_relation_proposal,assess_hierarchical_scope

_GRANT_KEY=os.urandom(32)


class _EvaluationAuthorization:
    def __init__(self,snapshot,budget,plan_sha):
        self.binding=fingerprint([snapshot['snapshot_id'],snapshot['scope'],snapshot['permission']])
        self.budget=budget;self.plan_sha=plan_sha
        self.seal=hmac.digest(_GRANT_KEY,canonical([self.binding,plan_sha]),'sha256')


def authorize_evaluation(snapshot,budget,plan_sha):
    if not isinstance(plan_sha,str) or not plan_sha or not budget.status().get('max_requests'):raise ValueError('evaluation_grant_invalid')
    return _EvaluationAuthorization(snapshot,budget,plan_sha)


def qualification_allows(proof,binding,limits):
    from hierarchical_comparison import evaluate_manifest
    try:
        if (not isinstance(proof,dict) or proof.get('schema')!='hierarchical-qualified-profile.v1'
                or proof['provider_fingerprint']!=fingerprint(binding['provider'])
                or proof['protocol_fingerprint']!=hierarchical_protocol_fingerprint()
                or proof.get('qualification_sha256')!=fingerprint({k:v for k,v in proof.items() if k!='qualification_sha256'})
                or any(type(proof.get(k)) is not int or proof[k]<limits[name] for k,name in (
                    ('input_bound','partition_input_tokens'),('output_bound','partition_output_tokens')))):
            return False
        result=evaluate_manifest(proof['evaluation'],proof['protocol_fingerprint'])
        return result['semantic_ready'] and result['answer_benefit_measured']
    except (KeyError,TypeError,ValueError):return False


def _evaluation_valid(value,snapshot,budget):
    return (isinstance(value,_EvaluationAuthorization) and value.budget is budget
        and value.binding==fingerprint([snapshot['snapshot_id'],snapshot['scope'],snapshot['permission']])
        and hmac.compare_digest(value.seal,hmac.digest(_GRANT_KEY,canonical([value.binding,value.plan_sha]),'sha256')))


def compute_invalidation(previous,current,dependencies):
    old={a['stable_id']:a['atom_id'] for a in previous.get('atoms',[])}
    new={a['stable_id']:a['atom_id'] for a in current.get('atoms',[])}
    changed=set(old[s] for s in old.keys()-new.keys())|set(current.get('affected_ids',[]))
    expanded=None
    if current.get('closure_verified') is not True:
        changed.update(old.values());expanded='selected_target_scope'
    pending=list(changed)
    while pending:
        for parent in dependencies.get(pending.pop(),[]):
            if parent not in changed:changed.add(parent);pending.append(parent)
    return {'stale_ids':sorted(changed),'reusable_stable_ids':sorted(old.keys()&new.keys()),
        'expanded_scope':expanded,'semantic_acceptance_reused':False}


def rebind_unchanged_leaf(previous_receipt,current_binding,verified_units):
    from .scenario_hierarchical_review import valid_review,VerifiedReview
    from copy import deepcopy
    if not valid_review(previous_receipt) or previous_receipt.get('status')!='reviewed' or previous_receipt.get('stage')!='leaf':return None
    old=previous_receipt['request'];binding=old['binding']
    if (old['inputs'].get('context_pages') or previous_receipt.get('review_axes')
            and previous_receipt['review_axes']['scope']['status']!='resolved'):return None
    if any(binding.get(k)!=current_binding.get(k) for k in ('protocol','protocol_fingerprint','wire_contract','scope','permission','selection_version','normalization_version','provider','provider_chain')):return None
    try:
        part=verified_units['partition'];prior=old['inputs']['partition']
        if part['context_only']!=prior['context_only'] or len(part['primary'])!=len(prior['primary']):return None
        rows={u['unit_id']:u for u in verified_units['units']};renames={}
        fields=('unit_id','role','turn_id','sequence','start','end','text','raw_line_sha256')
        for before,after in zip(prior['primary'],part['primary']):
            unit=rows[after['unit_id']]
            if (any(before.get(k)!=after.get(k) for k in fields) or unit['raw_line_sha256']!=after['raw_line_sha256']
                    or unit['role']!=after['role']):return None
            renames[before['span_id']]=after['span_id']
        proposal=deepcopy(old['inputs']['proposal'])
        for items in proposal.values():
            if not isinstance(items,list):return None
            for item in items:
                for ref in item['source_refs']:ref['span_id']=renames[ref['span_id']]
        # Preserve the ORIGINAL HTTP request and its budget proof. This is a
        # distinct host rebind, never a fabricated new model/HTTP receipt.
        return VerifiedReview({**dict(previous_receipt),'rebind':{'binding':current_binding,
            'inputs':{'partition':part,'proposal':proposal},'basis':'exact_raw_leaf_not_new_model_call'}})
    except (KeyError,TypeError):return None


def dispatch_hierarchical(job,snapshot,settings,provider,root,permission_getter,scope_getter,authorize_request,parent_lease_valid,base):
    limits=settings['limits'];budget=None
    if limits['model_requests'] and provider is not None:
        identity=fingerprint({k:snapshot[k] for k in ('scope','permission','selection_version','normalization_version')})
        try:
            budget=CoverageBudget(root/'requests.sqlite3',job_id=job['session_id'],budget_identity=snapshot['semantic_budget_identity'],
                parent_attempts=job['attempts'],max_requests=limits['model_requests'],max_tokens=limits['model_tokens'],scope_identity=identity)
        except ValueError as error:
            if str(error) not in {'budget_identity_changed','budget_scope_changed'}:raise
            try:budget=CoverageBudget.continue_generation(root/'requests.sqlite3',job_id=job['session_id'],scope_identity=identity,parent_attempts=job['attempts'])
            except ValueError:return {**base,'status':'budget_paused','reason':'parent_scope_changed_no_new_budget','review_protocol':'hierarchical_review.v1'}
    # Leave room for instructions, schema, proposals, aliases and envelope.
    # The exact envelope is checked again before every actual dispatch.
    parts=partition_snapshot(snapshot,capacity=max(4,limits['partition_input_tokens']//3),context_tokens=limits['context_tokens'])
    value=process_hierarchical_stages(job,snapshot,parts,settings,root=root,provider=provider,budget=budget,
        permission_getter=permission_getter,scope_getter=scope_getter,authorize_request=authorize_request,parent_lease_valid=parent_lease_valid)
    return {**base,**value}


def process_hierarchical_stages(job,snapshot,partitions,settings,*,root,provider,budget,permission_getter,
        scope_getter,authorize_request,parent_lease_valid,evaluation_authorization=None):
    from .scenario_hierarchical_pipeline import process
    return process(job,snapshot,partitions,settings,root=root,provider=provider,budget=budget,
        permission_getter=permission_getter,scope_getter=scope_getter,authorize_request=authorize_request,
        parent_lease_valid=parent_lease_valid,evaluation_authorization=evaluation_authorization)
