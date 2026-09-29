#!/usr/bin/env python3
"""Prepare auditable Luna/Sol Context summary jobs."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.context_summary import read_context_index
from lib.context_pipeline import prepare_jobs, write_queue, progress_snapshot, write_progress

parser = argparse.ArgumentParser()
parser.add_argument('--index', default=os.path.expanduser('~/.evolving-profile/context/context-index.json'))
parser.add_argument('--queue', default=os.path.expanduser('~/.evolving-profile/context/context-pipeline.json'))
parser.add_argument('--progress', default=os.path.expanduser('~/.evolving-profile/context/context-pipeline-progress.json'))
args = parser.parse_args()
queue = prepare_jobs(read_context_index(args.index))
receipt = write_queue(args.queue, queue)
progress = write_progress(args.progress, progress_snapshot(queue))
print(json.dumps({**receipt, **progress, 'status': queue['status']}, ensure_ascii=False, sort_keys=True))
