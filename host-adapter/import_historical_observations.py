#!/usr/bin/env python3
"""Backfill task-level process observations without promoting experience."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from lib.process_memory import ProcessMemoryStore

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('report',type=Path); ap.add_argument('--store',default=str(Path.home()/'.evolving-profile/process-memory/records.json')); args=ap.parse_args()
    data=json.loads(args.report.read_text(encoding='utf-8')); store=ProcessMemoryStore(args.store); existing={r.get('observation_key') for r in store.all() if r.get('kind')=='process_observation'}; added=0
    for c in data.get('categories',[]):
        key=f"historical:{c.get('session_id')}:{c.get('source_count')}:{c.get('signal_count')}"
        if key in existing: continue
        store.record_process_observation({'observation_key':key,'task_archetype':[c.get('task_archetype') or 'other'],'process_dimensions':c.get('process_dimensions') or ['observation'],'phase':'observe','outcome':'ambiguous','text':'历史任务过程观察：'+' '.join(c.get('source_excerpt') or [])[:2800],'primary_context':{'session_id':c.get('session_id')},'agent':{'role':'historical-codex-agent','host':'codex'},'model_profile':{'family':'historical_unknown','version':'pre_ep5_cutoff'},'environment_fingerprint':{'host':'codex_thread_history','cutoff':c.get('cutoff')},'source_trace_ids':[f"codex_thread_history:{c.get('session_id')}"],'rollout_state':'shadow','historical_candidate_id':key})
        added+=1
    print(json.dumps({'schema':'evolving-profile.historical-observations-import.v1','added':added,'total_candidates':len(data.get('categories',[])),'maturity':'observed','default_retrieval':'excluded'},ensure_ascii=False)); return 0
if __name__=='__main__': raise SystemExit(main())
