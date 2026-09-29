#!/usr/bin/env python3
"""Associate an exported Bank record list with Context without rewriting records."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.context_summary import read_context_index
from lib.context_associations import associate_records

parser = argparse.ArgumentParser()
parser.add_argument('--records', required=True)
parser.add_argument('--index', default=os.path.expanduser('~/.evolving-profile/context/context-index.json'))
parser.add_argument('--output', default=os.path.expanduser('~/.evolving-profile/context/context-associations.json'))
args = parser.parse_args()
records = json.loads(open(args.records, encoding='utf-8').read())
if isinstance(records, dict): records = records.get('records') or records.get('memories') or []
result = associate_records(records, read_context_index(args.index))
os.makedirs(os.path.dirname(args.output), exist_ok=True)
with open(args.output, 'w', encoding='utf-8') as handle: json.dump(result, handle, ensure_ascii=False, indent=2); handle.write('\n')
print(json.dumps({'ok': True, 'output': args.output, 'links': len(result['links']), 'unresolved': len(result['unresolved'])}, ensure_ascii=False, sort_keys=True))
