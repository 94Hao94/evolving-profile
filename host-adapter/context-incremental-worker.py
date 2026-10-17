#!/usr/bin/env python3
"""Discover Session changes and process bounded background Scenario jobs."""
import argparse
import json
import os
import time
from pathlib import Path

from lib.context_incremental import ContextIncremental, reassess_source_jobs, summary_runtime_permission


def load_provider(path, settings_path=None):
    from lib.scenario_coverage_provider import load_provider_config
    return load_provider_config(path,settings_path)


def recording_enabled(state_root):
    return summary_runtime_permission(state_root)['allowed']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', default=str(Path.home()/'.evolving-profile'))
    parser.add_argument('--session-root', default=str(Path.home()/'.codex/sessions'))
    parser.add_argument('--provider-env', help='Existing EP provider profile; no Codex model substitution')
    parser.add_argument('--bank-id', default=os.environ.get('EVOLVING_PROFILE_BANK_ID'), help='Explicit owning Bank; no inferred assignment')
    parser.add_argument('--session-id', action='append', help='Limit discovery and processing to exact Session IDs for scoped catch-up')
    parser.add_argument('--new-after', help='Only discover previously untracked Sessions created after this ISO time; existing jobs still update')
    parser.add_argument('--discover-only', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--reassess-source', action='store_true', help='Read-only source qualification plan; no discovery or model calls')
    parser.add_argument('--apply-reassessment', action='store_true', help='Apply only a reviewed exact-session reassessment plan')
    parser.add_argument('--expected-plan-sha256', help='Required dry-run digest for reassessment apply')
    parser.add_argument('--resume-remaining-budget', action='store_true', help='Explicit scoped recovery of eligible waiting jobs using only their remaining attempts')
    parser.add_argument('--process', action='store_true', help='Explicitly allow configured-provider background summaries')
    parser.add_argument('--coverage-source', action='store_true', help='Exact selected source coverage; shadow by default, no historical batch migration')
    parser.add_argument('--coverage-max-leases',type=int,default=64,help='At most 64 bounded decoder leases in one worker')
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--scan-limit', type=int, default=128)
    parser.add_argument('--max-jobs', type=int, default=4)
    parser.add_argument('--interval', type=int, default=30)
    parser.add_argument('--debounce', type=int, default=30)
    args = parser.parse_args()
    if args.coverage_source and (not args.session_id or len(args.session_id)>32 or args.process or args.watch or args.reassess_source or args.status or args.discover_only):
        parser.error('coverage-source requires 1-32 exact sessions and cannot combine with other actions')
    if not 1 <= args.max_jobs <= 32 or not 1 <= args.interval <= 3600 or not 0 <= args.debounce <= 3600:
        parser.error('invalid worker bounds')
    if args.process and args.discover_only: parser.error('choose process or discover-only')
    if args.apply_reassessment and not args.reassess_source: parser.error('apply requires reassess-source')
    if args.resume_remaining_budget and not args.reassess_source: parser.error('remaining budget recovery requires reassess-source')
    if args.reassess_source:
        if args.process or args.watch or args.status or args.discover_only:
            parser.error('reassessment cannot be combined with worker execution')
        try:
            receipt = reassess_source_jobs(args.state_root, args.session_root, session_ids=args.session_id,
                apply=args.apply_reassessment, expected_plan_sha256=args.expected_plan_sha256,
                resume_remaining_budget=args.resume_remaining_budget)
        except ValueError as error:
            parser.error(str(error))
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
        return 0
    worker = ContextIncremental(args.state_root, args.session_root, debounce=args.debounce, bank_id=args.bank_id, session_ids=args.session_id, new_after=args.new_after)
    if args.coverage_source:
        settings_path=Path(args.state_root)/'config/runtime-settings.json'
        settings=json.loads(settings_path.read_text()) if settings_path.is_file() else {}
        coverage=settings.get('scenario_coverage',{})
        from lib.scenario_coverage_contract import validate_settings
        effective=validate_settings(coverage)
        provider=None
        if effective['limits']['model_requests']:
            from lib.scenario_coverage_provider import ConfiguredCoverageProvider
            provider=ConfiguredCoverageProvider(load_provider(args.provider_env or str(Path(args.state_root)/'profiles/evolving-profile-api.env'),settings_path))
        results=[worker.process_coverage(sid,coverage,provider=provider,max_leases=args.coverage_max_leases) for sid in args.session_id]
        print(json.dumps({'coverage_jobs':results,'model_calls':sum(r['model_calls'] for r in results)},ensure_ascii=False),flush=True)
        return 0
    provider_path = args.provider_env or str(Path(args.state_root)/'profiles/evolving-profile-api.env')
    while True:
        if not args.status and not recording_enabled(args.state_root):
            print(json.dumps({'status':'disabled','model_calls':0}), flush=True)
            if not args.watch: return 0
            time.sleep(args.interval)
            continue
        discovery = {} if args.status else worker.discover(limit=args.scan_limit)
        results = []
        if args.process and not args.status:
            try: config = load_provider(provider_path,Path(args.state_root)/'config/runtime-settings.json')
            except (OSError, ValueError):
                print(json.dumps({'status':'waiting_provider_configuration', 'progress':worker.progress(), 'model_calls':0}))
                if not args.watch: return 2
            else:
                for _ in range(args.max_jobs):
                    result = worker.run_once(config)
                    results.append(result)
                    if result['status'] == 'idle': break
        print(json.dumps({'discovery':discovery, 'jobs':results, 'progress':worker.progress(),
                          'model_calls':0 if not args.process else 'background_processor_calls_not_counted'}, ensure_ascii=False), flush=True)
        if not args.watch: return 0
        time.sleep(args.interval)


if __name__ == '__main__':
    raise SystemExit(main())
