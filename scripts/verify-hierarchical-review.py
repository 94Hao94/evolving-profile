#!/usr/bin/env python3
"""Explicit isolated preflight/evaluation. No production job reset or publication."""
import argparse
import fcntl
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host-adapter'))
from lib.scenario_coverage_contract import canonical,fingerprint,coverage_permission,validate_settings
from lib.scenario_coverage_store import CoverageStore
from lib.scenario_coverage_incremental import process_coverage_job,_write
from lib.scenario_coverage_partition import partition_snapshot
from lib.scenario_hierarchical_plan import plan_hierarchical_work
from lib.scenario_coverage_budget import CoverageBudget
from lib.scenario_hierarchical_incremental import process_hierarchical_stages,authorize_evaluation
from hierarchical_comparison import evaluate_hierarchical_case
from lib.scenario_hierarchical_capacity import prepare_review_work
from lib.scenario_coverage_provider import ConfiguredCoverageProvider,load_provider_config


def prepare_case(snapshot,settings,provider):
    return prepare_review_work(snapshot,settings['limits'],provider)


def configured_provider(state_root):
    return ConfiguredCoverageProvider(load_provider_config(state_root/'profiles/evolving-profile-api.env',state_root/'config/runtime-settings.json'))


def authorized_execution(case,budget):
    return (type(case.get('minimum_requests')) is int and type(case.get('max_reserved_tokens')) is int
        and case['minimum_requests']>0 and case['max_reserved_tokens']>0
        and case['minimum_requests']<=budget['max_requests']-budget['requests_used']
        and case['max_reserved_tokens']<=budget['max_tokens']-budget['charged_tokens'])


def _budget_status(path):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        parents=[dict(r) for r in db.execute('SELECT * FROM parents')]
    if len(parents)!=1:raise ValueError('evaluation_grant_ambiguous')
    return CoverageBudget.existing_status(path,parents[0]['job'])


def _rows(state):return json.loads((state/'context/context-index.json').read_text())['sessions']


def preflight(args):
    previous=json.loads((args.baseline_root/'preflight.json').read_text());rows=_rows(args.state_root)
    selected=[dict(c,holdout=False) for c in previous['cases']]
    known={c['session_id'] for c in selected}
    candidates=[r for r in rows if r.get('session_id') not in known and r.get('status')=='model_reviewed'
        and r.get('bank_id') and r.get('project_key') and r.get('source_message_count',0)>0]
    # Stable sample selection is structural, not a keyword/model correctness
    # filter. Categories/gold remain unreviewed until independently inspected.
    candidates.sort(key=lambda r:(r.get('source_message_count',0),r['session_id']))
    for name,index in [('holdout-short',0),('holdout-medium',len(candidates)//2),('holdout-long',len(candidates)-1)]:
        if candidates:
            row=candidates[index]
            if row['session_id'] not in known:
                selected.append({'name':name,'session_id':row['session_id'],'holdout':True});known.add(row['session_id'])
    permission=coverage_permission(args.state_root);cases=[]
    try:provider=configured_provider(args.state_root)
    except (OSError,ValueError,TypeError):provider=None
    settings=validate_settings({'review_protocol':'hierarchical_review.v1'})
    for item in selected:
        row=next((r for r in rows if r.get('session_id')==item['session_id']),None)
        if row is None:cases.append({**item,'status':'unavailable','reason':'index_missing'});continue
        folder=args.output/'cases'/item['name']
        job={'session_id':row['session_id'],'bank_id':row.get('bank_id'),'project_key':row.get('project_key'),
            'permission':permission,'attempts':3,'status':'protected' if str(row.get('status','')).endswith('_protected') else 'waiting_source'}
        structural=process_coverage_job(job,args.session_root,{},store_root=folder)
        entry={**item,'status':structural['status'],'model_calls':0,'source_structure_complete':structural.get('source_manifest_complete',False),
            'task_category':'not_reviewed','used_for_tuning':False,'reference_status':'not_reviewed'}
        if structural.get('source_manifest_complete'):
            snapshot=CoverageStore(folder/'coverage.sqlite3',readonly=True).read(structural['snapshot_id'])
            if provider is None:
                entry.update(status='capacity_unverified',reason='ep_provider_configuration_unavailable')
                cases.append(entry);continue
            plan=prepare_case(snapshot,settings,provider)['plan']
            minimum=plan['minimum_requests']
            entry.update(snapshot_id=snapshot['snapshot_id'],scope=snapshot['scope'],source_revision=snapshot['location']['physical_revision'],
                unit_count=snapshot['selected_count'],minimum_requests=minimum,
                max_reserved_tokens=minimum*(settings['limits']['partition_input_tokens']*2+settings['limits']['partition_output_tokens']),
                cost_counting='conservative_utf8_bytes_not_measured_tokens',plan=plan)
        cases.append(entry)
    grant=args.baseline_root/'evaluation-requests.sqlite3'
    report={'schema':'hierarchical-evaluation-plan.v1','cases':cases,'model_calls':0,
        'shared_grant_ledger':str(grant),'budget':_budget_status(grant),'production_jobs_changed':False,
        'protocol_fingerprint':_protocol_fingerprint()}
    report['plan_sha256']=fingerprint(report)
    path=args.output/'plan.json'
    if path.exists():raise ValueError('frozen_plan_already_exists_choose_new_output')
    _write(path,report);return report


def _protocol_fingerprint():
    from lib.scenario_coverage_contract import hierarchical_protocol_fingerprint
    return hierarchical_protocol_fingerprint()


def execute(args):
    plan=json.loads((args.output/'plan.json').read_text())
    if (plan['plan_sha256']!=args.expected_plan_sha256 or fingerprint({k:v for k,v in plan.items() if k!='plan_sha256'})!=plan['plan_sha256']
            or plan['protocol_fingerprint']!=_protocol_fingerprint()):raise ValueError('evaluation_plan_changed')
    if args.grant_ledger.resolve()!=Path(plan['shared_grant_ledger']).resolve():raise ValueError('wrong_shared_grant')
    chosen=next((c for c in plan['cases'] if c['name']==args.case),None)
    status=_budget_status(args.grant_ledger)
    if chosen is None or chosen.get('plan',{}).get('status')!='planned' or not authorized_execution(chosen,status):
        return {'status':'budget_or_capacity_paused','model_calls':0,'budget':status}
    budget=CoverageBudget.continue_generation(args.grant_ledger,job_id=status['job'],scope_identity=status['scope_identity'],parent_attempts=status['attempts'])
    folder=args.output/'cases'/args.case
    snapshot=CoverageStore(folder/'coverage.sqlite3',readonly=True).read(chosen['snapshot_id'])
    permission=lambda:coverage_permission(args.state_root)
    def scope():
        row=next((r for r in _rows(args.state_root) if r.get('session_id')==chosen['session_id']),{})
        return {'session_id':chosen['session_id'],'bank_id':row.get('bank_id'),'project_key':row.get('project_key'),
            'identity_kind':'session_scoped_workspace_navigation_only'}
    provider=configured_provider(args.state_root)
    settings=validate_settings({'mode':'assisted','model_trial':True,'review_protocol':'hierarchical_review.v1'})
    prepared=prepare_case(snapshot,settings,provider)
    if prepared['plan']!=chosen['plan']:raise ValueError('evaluation_provider_or_capacity_changed')
    parts=prepared['source_partitions']
    grant=authorize_evaluation(snapshot,budget,plan['plan_sha256'])
    job={'session_id':chosen['session_id'],'attempts':3}
    result=process_hierarchical_stages(job,snapshot,parts,settings,root=folder,provider=provider,budget=budget,
        permission_getter=permission,scope_getter=scope,authorize_request=lambda:None,parent_lease_valid=None,evaluation_authorization=grant)
    result.update(case_id=chosen['name'],holdout=chosen['holdout'],used_for_tuning=chosen.get('used_for_tuning',False),requirements=[],
        session_id=chosen['session_id'],
        validated_protocol_fingerprint=_protocol_fingerprint(),source_evidence_fresh=CoverageStore(folder/'coverage.sqlite3',readonly=True).validate_snapshot(snapshot['snapshot_id'],permission())['valid'])
    result['evaluation']=evaluate_hierarchical_case(result)
    _write(folder/'hierarchical-result.json',result);return result


def assess_results(args):
    plan=json.loads((args.output/'plan.json').read_text());cases=[];manifest=[]
    protocol_current=plan['protocol_fingerprint']==_protocol_fingerprint()
    for entry in plan['cases']:
        folder=args.output/'cases'/entry['name']
        try:case=json.loads((folder/'hierarchical-result.json').read_text())
        except (OSError,ValueError):case={'failure':'not_executed','requirements':[]}
        try:
            reference=json.loads((folder/'independent-review.json').read_text())
            if (reference.get('snapshot_id')!=entry.get('snapshot_id') or reference.get('reviewed_without_producer_output') is not True):
                raise ValueError('reference_scope_or_independence_unverified')
            case.update(requirements=reference.get('requirements',[]),answer_comparison=reference.get('answer_comparison'),
                independent_review_sha256=fingerprint(reference))
        except (OSError,ValueError):case['independent_reference_status']='not_reviewed'
        case.update(case_id=entry['name'],session_id=entry['session_id'],snapshot_id=entry.get('snapshot_id'),
            validated_protocol_fingerprint=plan['protocol_fingerprint'],holdout=entry['holdout'])
        try:
            note=json.loads((folder/'case-reclassification.json').read_text())
            if note.get('snapshot_id')==entry.get('snapshot_id') and note.get('used_for_tuning') is True:
                case.update(used_for_tuning=True,holdout_reclassification_reason=note.get('reason'))
        except (OSError,ValueError):pass
        if entry.get('snapshot_id'):
            case['source_evidence_fresh']=CoverageStore(folder/'coverage.sqlite3',readonly=True).validate_snapshot(entry['snapshot_id'],coverage_permission(args.state_root))['valid']
        case['evaluation']=evaluate_hierarchical_case(case)
        if not protocol_current:case['evaluation'].update(semantic_ready=False,protocol_status='historical_not_current')
        cases.append(case);manifest.append({'case_id':entry['name'],'snapshot_id':entry.get('snapshot_id'),
            'requirements_sha256':fingerprint(case.get('requirements',[]))})
    report={'schema':'hierarchical-evaluation.v1','protocol_fingerprint':plan['protocol_fingerprint'],
        'plan_sha256':plan['plan_sha256'],'case_manifest':manifest,'case_manifest_sha256':fingerprint(manifest),
        'cases':cases,'protocol_current':protocol_current,'model_calls':0,'meaning':'Evaluation assembly adds no calls; case costs remain in the original grant.'}
    _write(args.output/'evaluation.json',report)
    return {'status':'evaluation_assembled','case_count':len(cases),'model_calls':0,
        'semantic_ready_cases':sum(c['evaluation']['semantic_ready'] for c in cases),
        'answer_benefit_measured_cases':sum(c['evaluation']['answer_benefit']=='measured' for c in cases)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-root','state-root','session-root','output'):p.add_argument('--'+name,type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--preflight',action='store_true');mode.add_argument('--execute',action='store_true');mode.add_argument('--assess',action='store_true')
    p.add_argument('--grant-ledger',type=Path);p.add_argument('--expected-plan-sha256');p.add_argument('--case')
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);args.output.chmod(0o700)
    lock=args.output/'evaluation.lock'
    with lock.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.execute and not all((args.grant_ledger,args.expected_plan_sha256,args.case)):p.error('execute requires original grant, frozen hash and explicit case')
        result=preflight(args) if args.preflight else assess_results(args) if args.assess else execute(args)
    print(json.dumps({k:v for k,v in result.items() if k not in {'cases','coverage','requirements'}},ensure_ascii=False))


if __name__=='__main__':main()
