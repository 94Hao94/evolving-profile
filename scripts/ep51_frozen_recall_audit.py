"""Freeze real candidate packs and replay their admission gate without network.

This evaluates candidate admission, not corpus-wide recall or answer accuracy.
Ground-truth seeds absent from the original backend response are never credited
as backend retrieval. All snapshots are private audit artifacts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def seal(snapshot):
    result = copy.deepcopy(snapshot)
    result.pop('sha256', None)
    return {**result, 'sha256': digest(result)}


def verify(snapshot):
    body = {key: value for key, value in snapshot.items() if key != 'sha256'}
    return snapshot.get('sha256') == digest(body)


def metrics(case, kept_ids):
    gold = set(case.get('expected_related_ids') or [])
    backend = set(case.get('backend_ids') or [])
    kept = set(kept_ids)
    denied = set(case.get('expected_rejected_ids') or [])
    return {'backend_positive_found': len(gold & backend), 'backend_positive_total': len(gold),
            'gate_positive_kept': len(gold & kept), 'gate_positive_total': len(gold),
            'unrelated_or_denied_kept': sorted(denied & kept),
            'missed_related': sorted(gold - kept)}


def write_private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    path.chmod(0o600)


def live_json(path, body=None):
    if not path.startswith('/v1/default/'):
        raise ValueError('unsupported_read_path')
    if body is not None and not path.endswith('/memories/recall'):
        raise ValueError('only_readonly_recall_post_allowed')
    request = urllib.request.Request('http://127.0.0.1:12088' + path,
                data=None if body is None else json.dumps(body).encode(),
                headers={'Content-Type': 'application/json'},
                method='GET' if body is None else 'POST')
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def capture(definitions, bank):
    bank_path = '/v1/default/banks/' + urllib.parse.quote(bank, safe='') + '/memories'
    sys.path.insert(0, str(REPO / 'host-adapter'))
    from lib.recall_source_context import enrich_source_context
    cases, chunks = [], {}
    for definition in definitions:
        query = definition['query']
        response = live_json(bank_path + '/recall', {'query': query,
              'types': ['world', 'experience'], 'budget': 'high', 'max_tokens': 8192})
        rows = copy.deepcopy(response.get('results') or [])
        backend_ids = [row['id'] for row in rows]
        seeds = []
        for memory_id in definition.get('expected_related_ids') or []:
            if memory_id not in backend_ids:
                rows.append(live_json(bank_path + '/' + urllib.parse.quote(memory_id, safe='')))
                seeds.append(memory_id)
        rows.extend(copy.deepcopy(definition.get('controls') or []))

        def source_api(path, **_kwargs):
            if not path.startswith('/v1/default/chunks/'):
                raise ValueError('unexpected_source_path')
            if path not in chunks:
                chunks[path] = live_json(path)
            return copy.deepcopy(chunks[path])

        enriched = enrich_source_context(query, rows, source_api, bank)
        cases.append({**definition, 'backend_ids': backend_ids,
                      'gate_only_seed_ids': seeds, 'records': rows,
                      'current_source_enriched_records': enriched})
    return seal({'schema': 'ep51.frozen-candidate-audit.v1', 'bank': bank,
                 'measurement_boundary': 'frozen_backend_candidate_admission_not_complete_bank_recall',
                 'cases': cases, 'chunks': chunks,
                 'current_gate_sha256': hashlib.sha256((REPO / 'host-adapter/lib/recall_relevance.py').read_bytes()).hexdigest()})


def gate_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay(snapshot, baseline):
    if not verify(snapshot):
        raise ValueError('frozen_snapshot_integrity_failed')
    gate_sha256 = hashlib.sha256((REPO / 'host-adapter/lib/recall_relevance.py').read_bytes()).hexdigest()
    if snapshot.get('current_gate_sha256') != gate_sha256:
        raise ValueError('frozen_current_gate_changed')
    current = gate_module(REPO / 'host-adapter/lib/recall_relevance.py', 'audit_current_gate')
    old = gate_module(Path(baseline), 'audit_baseline_gate')
    result = []
    for case in snapshot['cases']:
        before, before_detail = old.apply_relevance_policy(case['query'], copy.deepcopy(case['records']), 'weak')
        after, after_detail = current.apply_relevance_policy(case['query'], copy.deepcopy(case['current_source_enriched_records']), 'weak')
        ids_before, ids_after = [r['id'] for r in before], [r['id'] for r in after]
        result.append({'name': case['name'], 'query': case['query'],
                       'before': metrics(case, ids_before), 'after': metrics(case, ids_after),
                       'before_kept_ids': ids_before, 'after_kept_ids': ids_after,
                       'lost_before_kept_ids': sorted(set(ids_before) - set(ids_after)),
                       'gate_only_seed_ids': case['gate_only_seed_ids'],
                       'before_detail': before_detail, 'after_detail': after_detail})
    return {'schema': 'ep51.frozen-admission-comparison.v1',
            'snapshot_sha256': snapshot['sha256'], 'cases': result,
            'current_gate_sha256': gate_sha256,
            'current_policy_sha256': hashlib.sha256((REPO / 'config/recall-policy.json').read_bytes()).hexdigest(),
            'baseline_policy_sha256': hashlib.sha256((Path(baseline).parents[2] / 'config/recall-policy.json').read_bytes()).hexdigest(),
            'boundary': snapshot['measurement_boundary'],
            'all_labeled_related_kept': all(not row['after']['missed_related'] for row in result),
            'all_labeled_unrelated_or_denied_rejected': all(not row['after']['unrelated_or_denied_kept'] for row in result),
            'baseline_gate_sha256': hashlib.sha256(Path(baseline).read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-definitions')
    parser.add_argument('--bank')
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--baseline')
    parser.add_argument('--report')
    args = parser.parse_args()
    if args.capture_definitions:
        if not args.bank:
            parser.error('--bank required for capture')
        snapshot = capture(json.loads(Path(args.capture_definitions).read_text()), args.bank)
        write_private(args.snapshot, snapshot)
        print(json.dumps({'snapshot_sha256': snapshot['sha256'], 'cases': len(snapshot['cases'])}))
    else:
        if not args.baseline or not args.report:
            parser.error('--baseline and --report required for network-free replay')
        report = replay(json.loads(Path(args.snapshot).read_text()), args.baseline)
        write_private(args.report, report)
        print(json.dumps({key: report[key] for key in ('snapshot_sha256', 'all_labeled_related_kept',
                                                     'all_labeled_unrelated_or_denied_rejected')}))


if __name__ == '__main__':
    main()
