#!/usr/bin/env python3
"""EP host preparation CLI. Discovery is not installation or certification."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host-adapter'))
sys.path.insert(0,str(ROOT/'guidance'))
from lib.host_integration.registry import load_registry,get_profile,unique_object
from lib.host_integration.environment import discover_hosts,native_environment
from lib.host_integration.configuration import plan_configuration,apply_configuration,rollback_configuration
from lib.host_integration.guidance import render_host_guidance
from lib.host_integration.diagnostics import diagnostic_report
from lib.host_integration.observations import project_observations,record_probe
from ep_platform_lock import atomic_replace_bytes


def launch_configuration(host,mode,state_root):
    if mode!='local':raise ValueError('target_environment_requires_explicit_launch_configuration')
    return {'command':sys.executable,'args':[str(ROOT/'host-adapter/evolving_profile_controller_mcp.py')],
            'env':{'EVOLVING_PROFILE_HOST_ID':host,'EVOLVING_PROFILE_ACCESS_MODE':'read-only',
                   'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8',
                   'EVOLVING_PROFILE_GUIDANCE_SRC':str(ROOT/'guidance'),
                   'EVOLVING_PROFILE_STATE_ROOT':str(state_root)}}


def dependency_report():
    return {'platform_lock':{'available':os.name in ('nt','posix'),'execution_platform':sys.platform},
            'python':{'version':sys.version.split()[0],'interpreter':sys.executable},
            'api':{'status':'not_started_or_certified'},'controller':{'status':'not_started_or_certified'},
            'worker':{'status':'not_started_or_certified'},'local_models':{'status':'not_loaded_or_certified'},
            'service_management':{'status':'not_verified'},'windows_execution':'not_run' if os.name!='nt' else 'current_os_only_not_full_acceptance'}


def _stored_json(path,root):
    actual=Path(path).resolve();expected=root.resolve()
    if not actual.is_relative_to(expected) or actual.is_symlink() or actual.stat().st_size>1024*1024:
        raise ValueError('plan_or_receipt_scope_rejected')
    return json.loads(actual.read_text(encoding='utf-8'),object_pairs_hook=unique_object)


def execute(args):
    registry=load_registry();profile=get_profile(registry,args.host) if args.host else None
    root=Path(args.state_root).absolute()
    if args.action=='list':return registry
    if args.action=='matrix':
        from lib.host_integration.acceptance import render_matrix
        return render_matrix(registry,args.locale)
    if args.action=='guide':
        if profile is None:raise ValueError('host_required')
        return render_host_guidance(profile,{},args.locale)
    environment=native_environment(include_apps=args.action in ('discover','doctor','export-diagnostics'))
    environment['mode']=args.mode
    if args.action in ('discover','doctor'):
        selected={**registry,'profiles':[profile]} if profile else registry
        report=project_observations(discover_hosts(selected,environment,{'bypass_cache':True}),registry,root,ROOT)
        report.update(provider_calls=0,host_tasks_started=0,dependencies=dependency_report())
        if args.probe:
            if not profile:raise ValueError('host_required')
            from lib.host_integration.protocol import probe_stdio
            launch=launch_configuration(profile['id'],args.mode,root)
            # initialize/list cannot consume private guidance or ingress during this readiness test.
            import tempfile
            with tempfile.TemporaryDirectory(prefix='ep-protocol-') as temp:
                runner='import runpy,sys;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[2]).parent));Path.home=classmethod(lambda cls:Path(sys.argv[1]));runpy.run_path(sys.argv[2],run_name="__main__")'
                command=[sys.executable,'-c',runner,temp,launch['args'][0]]
                env={**os.environ,**launch['env'],'EVOLVING_PROFILE_GUIDANCE_CONFIG':str(Path(temp)/'absent.json')}
                report['protocol_probe']=probe_stdio(command,env)
                record_probe(root,report['hosts'][0],report['protocol_probe'])
                report=project_observations(report,registry,root,ROOT)
        return report
    if profile is None:raise ValueError('host_required')
    if args.action=='config-preview':
        paths=profile['config'].get('paths',{}).get(environment['platform'],[])
        desired=launch_configuration(profile['id'],args.mode,root)
        if not args.target and not paths:
            return {'schema':'ep.host-config-plan.v1','host_id':profile['id'],'apply_supported':False,
                    'status':'manual_import_required','desired':desired,'sources':profile.get('sources',[])}
        target=Path(args.target) if args.target else Path.home()/paths[0]
        plan=plan_configuration(profile,target,desired)
        if args.save_plan:
            location=root/'host-integrations/plans'/f"{plan['plan_id']}.json"
            atomic_replace_bytes(location,(json.dumps(plan,ensure_ascii=False,indent=2)+'\n').encode())
            plan['saved_plan']=str(location)
        return plan
    if args.action in ('config-apply','config-rollback'):
        if not args.confirm or args.expected_sha256 is None:raise ValueError('explicit_confirmation_and_revision_required')
        expected=None if args.expected_sha256=='absent' else args.expected_sha256
        if args.action=='config-apply':
            if not args.plan:raise ValueError('saved_plan_required')
            plan=_stored_json(args.plan,root/'host-integrations/plans')
            if plan.get('host_id')!=profile['id']:raise ValueError('plan_host_mismatch')
            receipt=apply_configuration(plan,expected_sha256=expected)
            location=root/'host-integrations/receipts'/f"{plan['plan_id']}.json"
            atomic_replace_bytes(location,(json.dumps(receipt,indent=2)+'\n').encode())
            return {**receipt,'saved_receipt':str(location)}
        if not args.receipt:raise ValueError('saved_receipt_required')
        receipt=_stored_json(args.receipt,root/'host-integrations/receipts')
        if receipt.get('host_id')!=profile['id']:raise ValueError('receipt_host_mismatch')
        return rollback_configuration(receipt,expected_sha256=expected)
    if args.action=='export-diagnostics':
        report=discover_hosts({**registry,'profiles':[profile]},environment)
        events=[{'host_id':row['host_id'],'status':row['status'],'platform':environment['platform'],
                 'state':row['installation']['state']} for row in report['hosts']]
        return diagnostic_report(events)
    raise ValueError('unknown_action')


def main():
    # MCP/config JSON uses UTF-8 regardless of a Windows/legacy terminal codepage.
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['list','discover','doctor','guide','config-preview','config-apply','config-rollback','export-diagnostics','matrix'])
    parser.add_argument('--host');parser.add_argument('--mode',choices=['local','wsl','remote'],default='local')
    parser.add_argument('--state-root',default=os.environ.get('EVOLVING_PROFILE_STATE_ROOT',str(Path.home()/'.evolving-profile')))
    parser.add_argument('--locale',default='en');parser.add_argument('--json',action='store_true')
    parser.add_argument('--target');parser.add_argument('--plan');parser.add_argument('--receipt')
    parser.add_argument('--expected-sha256');parser.add_argument('--save-plan',action='store_true')
    parser.add_argument('--confirm',action='store_true');parser.add_argument('--probe',action='store_true')
    parser.add_argument('--format',choices=['json','markdown'],default='json')
    args=parser.parse_args()
    try:
        result=execute(args)
        print(result if isinstance(result,str) else json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        # Do not echo path/credential-bearing raw exception messages.
        code=str(exc) if isinstance(exc,ValueError) and str(exc).replace('_','').isalnum() else 'operation_unavailable'
        print(json.dumps({'schema':'ep.host-diagnostics.v1','status':'failed','error_code':code}))
        return 2


if __name__=='__main__':raise SystemExit(main())
