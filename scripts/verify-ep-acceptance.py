#!/usr/bin/env python3
"""Repeatable engineering gates and honest declared-scope semantic readiness.

No Provider requests, job retries, configuration writes, Git mutations or release
publication. --run-engineering only runs the fixed local test/build commands.
"""
import argparse,hashlib,json,sqlite3,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host-adapter'))

REQUIRED=('backend','console','typescript','build','package')


def source_fingerprint(root):
    rows=[]
    for folder in ('host-adapter','guidance','status','controller','console/src','console/tests','config','scripts'):
        for p in sorted((root/folder).rglob('*')):
            if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or p.suffix not in {'.py','.ts','.tsx','.json','.sh','.mjs'}:continue
            rows.append((str(p.relative_to(root)),hashlib.sha256(p.read_bytes()).hexdigest()))
    for name in ('VERSION','console/package.json','console/package-lock.json'):
        p=root/name
        if p.is_file():rows.append((name,hashlib.sha256(p.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()


def protocol_fingerprint(root):
    files=['host-adapter/lib/scenario_coverage_review.py','host-adapter/lib/scenario_global_review.py',
        'host-adapter/lib/scenario_coverage_partition.py','host-adapter/lib/scenario_intent_ledger.py','config/scenario-coverage-contract.json']
    return hashlib.sha256(b''.join(hashlib.sha256((root/f).read_bytes()).digest() for f in files)).hexdigest()


def assess(report,current_fingerprint,current_protocol=None,*,current_hierarchical_protocol=None):
    report=report if isinstance(report,dict) else {}
    raw=report.get('checks');checks=[c for c in raw if isinstance(c,dict)] if isinstance(raw,list) else []
    names=[c.get('name') for c in checks]
    valid=report.get('source_fingerprint')==current_fingerprint and report.get('source_unchanged_during_checks') is True and all(names.count(name)==1 for name in REQUIRED)
    engineering=valid and all(type(next(c for c in checks if c.get('name')==name).get('exit_code')) is int
        and next(c for c in checks if c.get('name')==name)['exit_code']==0 for name in REQUIRED)
    cases=report.get('semantic_cases');cases=cases if isinstance(cases,list) else []
    def semantic_valid(c):
        if not isinstance(c,dict) or not isinstance(c.get('coverage'),dict):return False
        cov=c['coverage']
        return (isinstance(current_protocol,str) and bool(current_protocol) and c.get('validated_protocol_fingerprint')==current_protocol
            and c.get('source_evidence_fresh') is True and c.get('failure') is None
            and c.get('evaluation_scope')=='full' and c.get('source_structure_complete') is True
            and cov.get('status')=='accepted' and cov.get('semantic_review_status')=='automated_declared_scope_accepted'
            and cov.get('source_manifest_complete') is True
            and all(cov.get(k)==[] for k in ('missing_part_ids','missing_local_partition_ids','conflicts'))
            and c.get('external_fact_verified') is False)
    semantics=bool(cases) and all(semantic_valid(c) for c in cases)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host-adapter'))
    from hierarchical_comparison import evaluate_manifest
    hierarchical=evaluate_manifest(report.get('hierarchical_evaluation'),current_hierarchical_protocol)
    return {'schema':'evolving-profile.acceptance-gate.v1','engineering_status':'passed' if engineering else 'incomplete_or_failed',
        'semantic_status':'passed' if semantics else 'incomplete','release_ready':bool(engineering and semantics),
        'source_fingerprint_matches':report.get('source_fingerprint')==current_fingerprint,
        'semantic_case_count':len(cases),'answer_adoption':'not_measured','external_fact_verified':False,
        'hierarchical_semantic_ready':bool(engineering and hierarchical['semantic_ready']),
        'hierarchical_case_count':len(report.get('hierarchical_evaluation',{}).get('cases',[])) if isinstance(report.get('hierarchical_evaluation'),dict) and isinstance(report['hierarchical_evaluation'].get('cases'),list) else 0,
        'answer_benefit_measured':bool(engineering and hierarchical['answer_benefit_measured']),
        'boundary':'Current source and protocol-bound supplied evidence only; not an independent signed model attestation, all-history coverage, accuracy guarantee or GitHub authorization.'}


def current_semantic_case(case,case_root,state_root,root):
    result=dict(case) if isinstance(case,dict) else {'failure':'invalid_case'}
    result['source_evidence_fresh']=False
    if state_root is None:return result
    sys.path.insert(0,str(root/'host-adapter'))
    try:
        from lib.scenario_coverage_store import CoverageStore
        from lib.scenario_coverage_contract import coverage_permission
        snap=CoverageStore(case_root/'coverage.sqlite3',readonly=True).read(result['snapshot_id'])
        index=json.loads((state_root/'context/context-index.json').read_text())
        row=next(r for r in index['sessions'] if r['session_id']==result['session_id'])
        scope=snap['scope']
        matched=scope.get('session_id')==result['session_id'] and all(scope.get(k)==row.get(k) for k in ('bank_id','project_key'))
        result['source_evidence_fresh']=bool(matched and CoverageStore(case_root/'coverage.sqlite3',readonly=True).validate_snapshot(result['snapshot_id'],coverage_permission(state_root))['valid'])
    except (OSError,ValueError,KeyError,TypeError,StopIteration,sqlite3.Error):pass
    return result


def run_engineering(root,out):
    commands={'backend':[sys.executable,'-m','pytest','-q','host-adapter','guidance','status','controller/test_evolution_recall.py','scripts/test_ep_acceptance_gate.py','scripts/test_hierarchical_evaluation.py'],
        'console':['npm','test'],'typescript':['npx','tsc','--noEmit'],'build':['npm','run','build'],'package':['bash','scripts/verify-package.sh']}
    before=source_fingerprint(root);checks=[]
    for name in REQUIRED:
        work=root/'console' if name in {'console','typescript','build'} else root
        log=out/(name+'.log')
        with log.open('x') as stream:
            try:code=subprocess.run(commands[name],cwd=work,stdout=stream,stderr=subprocess.STDOUT,timeout=1200,check=False).returncode
            except subprocess.TimeoutExpired:code=124
        checks.append({'name':name,'command':commands[name],'exit_code':code,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()})
        print(json.dumps({'gate':name,'exit_code':code}),flush=True)
    return {'source_fingerprint':before,'source_unchanged_during_checks':source_fingerprint(root)==before,'checks':checks}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--evidence-root',type=Path,required=True)
    parser.add_argument('--run-engineering',action='store_true');parser.add_argument('--semantic-root',type=Path);parser.add_argument('--state-root',type=Path)
    parser.add_argument('--hierarchical-root',type=Path)
    args=parser.parse_args();root=args.root.resolve();out=args.evidence_root.resolve();out.mkdir(parents=True,exist_ok=True)
    if args.run_engineering:
        report=run_engineering(root,out)
        (out/'engineering.json').write_text(json.dumps(report,indent=2))
    else:
        try:report=json.loads((out/'engineering.json').read_text())
        except (OSError,ValueError):report={}
    cases=[]
    if args.semantic_root:
        for p in sorted((args.semantic_root/'cases').glob('*/result.json')):
            try:case=json.loads(p.read_text())
            except (OSError,ValueError):case={'failure':'case_unreadable'}
            cases.append(current_semantic_case(case,p.parent,args.state_root,root))
    report['semantic_cases']=cases
    if args.hierarchical_root:
        try:
            path=args.hierarchical_root/'evaluation.json'
            if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError('evaluation_path_invalid')
            with path.open('rb') as stream:raw=stream.read(64*1024*1024+1)
            if len(raw)>64*1024*1024:raise ValueError('evaluation_size_invalid')
            evaluation=json.loads(raw)
            if not isinstance(evaluation,dict) or not isinstance(evaluation.get('cases'),list):raise ValueError('evaluation_shape_invalid')
            refreshed=[]
            for case in evaluation['cases']:
                name=case.get('case_id') if isinstance(case,dict) else None
                if not isinstance(name,str) or not name or len(name)>100 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in name):
                    refreshed.append({'failure':'invalid_case_identity'});continue
                refreshed.append(current_semantic_case(case,args.hierarchical_root/'cases'/name,args.state_root,root))
            report['hierarchical_evaluation']={**evaluation,'cases':refreshed}
        except (OSError,ValueError,TypeError):report['hierarchical_evaluation']={'failure':'unreadable_or_invalid_evaluation'}
    from lib.scenario_coverage_contract import hierarchical_protocol_fingerprint
    result=assess(report,source_fingerprint(root),protocol_fingerprint(root),current_hierarchical_protocol=hierarchical_protocol_fingerprint(root))
    if args.state_root:
        sys.path.insert(0,str(root/'host-adapter'))
        from lib.scenario_recovery_readiness import recovery_readiness
        dbpath=(args.state_root/'context/context-incremental.sqlite').resolve()
        with sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            result['recovery_items']=[recovery_readiness(dict(r)) for r in db.execute("SELECT session_id,status,attempts,error_code FROM jobs WHERE status IN ('failed','waiting_source','retrying','protected')")]
    (out/'acceptance.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result));return 0 if result['release_ready'] else 2


if __name__=='__main__':raise SystemExit(main())
