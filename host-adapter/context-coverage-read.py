#!/usr/bin/env python3
"""Read-only scoped projection for Console; never invokes a Provider."""
import argparse
import json
from pathlib import Path
from lib.scenario_coverage_contract import coverage_permission,validate_settings
from lib.scenario_coverage_read import read_coverage_view


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',required=True)
    parser.add_argument('--session-id',required=True)
    parser.add_argument('--view',choices=['overview','requirements','relations','source'],default='overview')
    parser.add_argument('--requirement-id')
    parser.add_argument('--cursor')
    parser.add_argument('--bank-id');parser.add_argument('--project-key')
    args=parser.parse_args();root=Path(args.state_root)
    scope={k:v for k,v in {'bank_id':args.bank_id,'project_key':args.project_key}.items() if v is not None}
    try:
        settings_path=root/'config/runtime-settings.json'
        settings=json.loads(settings_path.read_text()) if settings_path.is_file() else {}
        protocol=validate_settings(settings.get('scenario_coverage'))['review_protocol']
        if args.view=='source':
            if settings.get('modules',{}).get('source_readback',{}).get('retrieve') is not True:raise ValueError('source_readback_disabled')
        value=read_coverage_view(root/'context/coverage',args.session_id,args.view,cursor=args.cursor,permission=coverage_permission(root),expected_scope=scope,requirement_id=args.requirement_id,review_protocol=protocol)
    except ValueError as error:
        reason=str(error);known=reason in {'coverage_cursor_stale_source_or_permission','coverage_scope_changed','coverage_inventory_stale','coverage_cursor_stale_or_invalid'}
        value={'status':'stale' if known else 'unavailable','reason':reason if known else 'coverage_unavailable','source_readback':False}
    except (OSError,KeyError):value={'status':'unavailable','reason':'coverage_unavailable','source_readback':False}
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':main()
