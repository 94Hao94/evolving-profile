"""Byte-identical visible records are distinct source occurrences, not one ID."""
import copy
import json

import pytest

from lib import scenario_model
from lib.context_incremental import _input_revision
from lib.scenario_episodes import partition_source
from lib.scenario_source import read_session_source, revision_for_messages

SID = '00000000-0000-4000-8000-000000000081'


def write_source(tmp_path, *, adjacent=False, same_turn=False):
    # Mirrors the Claude bridge rollout: the message row itself has no turn ID;
    # a preceding turn_context distinguishes identical serialized user records.
    def turn(value):
        return {'type': 'turn_context', 'payload': {'turn_id': value}}
    def user(text):
        return {'type': 'response_item', 'payload': {'type': 'message',
            'role': 'user', 'content': [{'type': 'input_text', 'text': text}]}}
    repeated = user('请继续检查。')
    rows = [turn('t0'), user('请检查系统兼容性。'), turn('t1'), repeated]
    if not adjacent:
        rows += [turn('t2'), user('保留原文证据。')]
    rows += [turn('t1' if same_turn else 't3'), repeated]
    path = tmp_path / f'rollout-test-{SID}.jsonl'
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    return path, read_session_source(SID, tmp_path)


@pytest.mark.parametrize('adjacent', [False, True])
def test_repeated_raw_records_keep_exact_episode_decision_coverage(tmp_path, monkeypatch, adjacent):
    _, source = write_source(tmp_path, adjacent=adjacent)
    calls = []
    def classify(source, targets, **kwargs):
        calls.extend(targets)
        return [{'message_id': mid, 'decision': 'uncertain',
                 'method': 'model_boundary_review'} for mid in targets]
    monkeypatch.setattr(scenario_model, '_request_episode_decisions', classify)
    result = scenario_model.request_episode_bundle(source, base_url='https://test.invalid',
                                                   api_key='test', model='test')
    expected = [row['evidence_id'] for row in source['messages'][1:]]
    assert result['status'] == 'episode_boundary_unresolved'
    assert calls == expected  # Distinct turns must not become same_turn_join.
    assert [row['message_id'] for row in result['boundary_decisions']] == expected
    assert len(set(expected)) == len(expected)
    parts = partition_source(source, expected)
    assert [mid for part in parts for mid in part['message_ids']] == [
        row['evidence_id'] for row in source['messages']]


def test_repeated_raw_record_occurrences_preserve_evidence_and_append_stability(tmp_path):
    path, source = write_source(tmp_path)
    rows = source['messages']
    assert len({row['evidence_id'] for row in rows}) == len(rows)
    assert rows[1]['raw_line_sha256'] == rows[3]['raw_line_sha256']
    assert rows[1]['byte_offset'] != rows[3]['byte_offset']
    assert rows[1]['turn_id'] != rows[3]['turn_id']
    assert rows[1]['evidence_id'] == rows[1]['raw_line_sha256'][:16]
    before = [row['evidence_id'] for row in rows]
    with path.open('a') as handle:
        handle.write(json.dumps({'type': 'turn_context', 'payload': {'turn_id': 't4'}}) + '\n')
        handle.write(path.read_text().splitlines()[3] + '\n')
    reread = read_session_source(SID, tmp_path)
    assert [row['evidence_id'] for row in reread['messages'][:-1]] == before
    assert len({row['evidence_id'] for row in reread['messages']}) == len(rows) + 1


def test_disambiguated_ids_invalidate_old_snapshot_without_resetting_semantic_budget(tmp_path):
    _, source = write_source(tmp_path)
    legacy = copy.deepcopy(source)
    for row in legacy['messages']:
        row['evidence_id'] = row['raw_line_sha256'][:16]
    legacy['source_revision'] = revision_for_messages(legacy['messages'])
    assert source['source_revision'] != legacy['source_revision']
    assert _input_revision(source, 'project', 'bank') == _input_revision(legacy, 'project', 'bank')


def test_identical_records_within_one_turn_are_unique_but_joined(tmp_path, monkeypatch):
    _, source = write_source(tmp_path, adjacent=True, same_turn=True)
    def classify(source, targets, **kwargs):
        return [{'message_id': mid, 'decision': 'uncertain',
                 'method': 'model_boundary_review'} for mid in targets]
    monkeypatch.setattr(scenario_model, '_request_episode_decisions', classify)
    result = scenario_model.request_episode_bundle(source, base_url='https://test.invalid',
                                                   api_key='test', model='test')
    assert len({row['evidence_id'] for row in source['messages']}) == 3
    assert [row['message_id'] for row in result['boundary_decisions']] == [
        row['evidence_id'] for row in source['messages'][1:]]
    assert result['boundary_decisions'][-1]['method'] == 'same_turn_join'


def test_unique_record_ids_and_revision_remain_legacy_compatible(tmp_path):
    path, _ = write_source(tmp_path)
    # Remove the repeated occurrence and its turn context.
    path.write_text('\n'.join(path.read_text().splitlines()[:-2]) + '\n')
    source = read_session_source(SID, tmp_path)
    canonical = [{key: row.get(key) for key in ('raw_line_sha256', 'role', 'text', 'turn_id')}
                 for row in source['messages']]
    import hashlib
    from lib.scenario_source import NORMALIZATION_VERSION
    legacy_revision = hashlib.sha256(json.dumps(
        {'normalization_version': NORMALIZATION_VERSION, 'messages': canonical},
        ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert source['source_revision'] == legacy_revision
    assert all(row['evidence_id'] == row['raw_line_sha256'][:16] for row in source['messages'])
