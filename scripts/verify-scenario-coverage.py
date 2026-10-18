#!/usr/bin/env python3
"""Explicit real-source shadow replay. No Provider calls, source edits or v3 promotion."""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host-adapter'))
from lib.scenario_coverage_incremental import process_coverage_job
from lib.scenario_source_codec import locate_source,physical_revision


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root',required=True);parser.add_argument('--session-root',required=True)
    parser.add_argument('--session-id',action='append',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if not 1<=len(args.session_id)<=32:parser.error('select 1-32 exact sessions')
    state=Path(args.state_root);index=json.loads((state/'context/context-index.json').read_text())
    rows={r['session_id']:r for r in index['sessions']}
    results=[]
    with tempfile.TemporaryDirectory(prefix='ep-coverage-replay-') as folder:
        for sid in args.session_id:
            row=rows[sid];loc=locate_source(sid,args.session_root)
            if str(row.get('status','')).endswith('_protected'):
                results.append({'session_id':sid,'status':'protected','model_calls':0});continue
            before=physical_revision(loc['path']) if loc['status']=='ready' else None
            job={'session_id':sid,'bank_id':row.get('bank_id'),'project_key':row.get('project_key'),
                'attempts':3,'status':'waiting_source','permission':{'allowed':True,'version':'isolated-readonly-replay.v1'}}
            result=process_coverage_job(job,args.session_root,{},store_root=Path(folder).resolve()/sid,
                provider=lambda p:(_ for _ in ()).throw(AssertionError('shadow_must_not_call_provider')))
            after=physical_revision(loc['path']) if loc['status']=='ready' else None
            if before!=after:result.update(status='stale',reason='live_source_changed_during_replay')
            if result['model_calls']!=0 or result['published']:raise AssertionError('shadow_side_effect')
            results.append(result)
    output=Path(args.output)
    with output.open('x') as stream:json.dump({'source_count':len(results),'model_calls':0,'results':results},stream,ensure_ascii=False,indent=2)
    output.chmod(0o600)
    print(json.dumps({'sources':len(results),'model_calls':0,'statuses':{status:sum(r['status']==status for r in results) for status in {r['status'] for r in results}}}))


if __name__=='__main__':main()
