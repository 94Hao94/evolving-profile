"""Normalization and legacy observations must not replenish model attempts."""
import json
import uuid

import pytest

from lib.context_incremental import ContextIncremental, INPUT_REVISION_SCHEME, _input_revision
from lib.scenario_source import read_session_source
from test_context_incremental import rollout
from test_context_semantic_reuse import append_tool


def existing_job(tmp_path, *, status, attempts, qualification, old_signature):
    sid = str(uuid.uuid4())
    root = tmp_path / 'sessions'
    path = rollout(root, sid, text='[$sample](/skills/sample/SKILL.md)\n请保留原始预算。')
    definition = ('<skill>\n<name>sample</name>\n<path>/skills/sample/SKILL.md</path>\n'
                  '---\nname: sample\ndescription: Fixture reference\n---\n'
                  'This complete skill definition is reference context.\n</skill>')
    with path.open('a') as stream:
        stream.write(json.dumps({'type': 'response_item', 'payload': {'type': 'message',
            'role': 'user', 'content': [{'type': 'input_text', 'text': definition}]}}) + '\n')
    worker = ContextIncremental(tmp_path / 'state', root)
    worker.discover(now=100)
    source = read_session_source(sid, root, max_chars=60000)
    assert len(source['_budget_messages']) == 2 and len(source['messages']) == 1
    if callable(old_signature):
        old_signature = old_signature(source)
    with worker.db() as db:
        db.execute('UPDATE jobs SET status=?,attempts=?,error_code=?,input_revision=?,input_qualification=?',
                   (status, attempts, 'scenario_over_budget', old_signature, json.dumps(qualification)))
    append_tool(path)
    worker.discover(now=300)
    return worker, sid, path, source


def no_provider(*_args, **_kwargs):
    pytest.fail('A source-only baseline observation reached the model processor')


@pytest.mark.parametrize('status', ['waiting_source', 'source_not_applicable', 'failed', 'protected'])
@pytest.mark.parametrize('attempts', [1, 3])
@pytest.mark.parametrize('qualification', [{}, {'input_revision_scheme': INPUT_REVISION_SCHEME}, None])
@pytest.mark.parametrize('old_signature', ['0' * 64, None])
def test_incomparable_terminal_baseline_preserves_status_and_spent_attempts(tmp_path, status, attempts, qualification, old_signature):
    worker, sid, _, _ = existing_job(tmp_path, status=status, attempts=attempts,
        qualification=qualification, old_signature=old_signature)
    result = worker.run_once({}, now=400, processor=no_provider)
    assert result['status'] == status and result['provider_calls'] == 0
    assert result['legacy_source_revision_unknown'] is True
    with worker.db() as db:
        row = db.execute('SELECT status,attempts,source_check_pending FROM jobs').fetchone()
        assert tuple(row) == (status, attempts, 0)
        witness = json.loads(db.execute('SELECT value FROM metadata WHERE key=?',
                            ('legacy-observed:' + sid,)).fetchone()[0])
        assert witness['prior_attempts'] == attempts


@pytest.mark.parametrize('status', ['waiting_source', 'source_not_applicable', 'failed', 'protected'])
@pytest.mark.parametrize('attempts', [1, 3])
def test_eligibility_only_signature_change_preserves_terminal_budget(tmp_path, status, attempts):
    qualification = {'input_revision_scheme': INPUT_REVISION_SCHEME, 'source_status': 'over_budget'}
    worker, _, _, source = existing_job(tmp_path, status=status, attempts=attempts,
        qualification=qualification,
        old_signature=lambda source: _input_revision({**source, 'status': 'over_budget'}, '/workspace/demo', None))
    result = worker.run_once({}, now=400, processor=no_provider)
    assert result['status'] == status and result['provider_calls'] == 0
    assert result['unchanged_source'] is True
    with worker.db() as db:
        row = db.execute('SELECT status,attempts,source_check_pending,input_revision FROM jobs').fetchone()
        assert tuple(row[:3]) == (status, attempts, 0)
        # This is a comparison-baseline migration, never a fresh model budget.
        assert row['input_revision'] == _input_revision(source, '/workspace/demo', None)


@pytest.mark.parametrize('attempts,expected_status,expected_calls,expected_attempts', [
    (1, 'retrying', 1, 2), (3, 'failed', 0, 3)])
def test_active_status_only_change_can_only_spend_existing_remaining_attempts(
        tmp_path, attempts, expected_status, expected_calls, expected_attempts):
    qualification = {'input_revision_scheme': INPUT_REVISION_SCHEME, 'source_status': 'over_budget'}
    worker, _, _, _ = existing_job(tmp_path, status='retrying', attempts=attempts,
        qualification=qualification,
        old_signature=lambda source: _input_revision({**source, 'status': 'over_budget'}, '/workspace/demo', None))
    calls = []
    def invalid(*_args):
        calls.append(1)
        raise ValueError('scenario_state_invalid')
    result = worker.run_once({}, now=400, processor=invalid)
    assert result['status'] == expected_status and len(calls) == expected_calls
    with worker.db() as db:
        assert db.execute('SELECT attempts FROM jobs').fetchone()[0] == expected_attempts


def test_known_scheme_actual_new_message_still_starts_legitimate_new_budget(tmp_path):
    qualification = {'input_revision_scheme': INPUT_REVISION_SCHEME, 'source_status': 'complete'}
    worker, _, path, _ = existing_job(tmp_path, status='waiting_source', attempts=3,
        qualification=qualification,
        old_signature=lambda source: _input_revision(source, '/workspace/demo', None))
    with path.open('a') as stream:
        stream.write(json.dumps({'type': 'turn_context', 'payload': {'turn_id': 'new-turn'}}) + '\n')
        stream.write(json.dumps({'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
            'content': [{'type': 'input_text', 'text': 'A new substantive request'}]}}) + '\n')
    worker.discover(now=500)
    calls = []
    def invalid(*_args):
        calls.append(1)
        raise ValueError('scenario_state_invalid')
    result = worker.run_once({}, now=700, processor=invalid)
    assert result['status'] == 'retrying' and len(calls) == 1
    with worker.db() as db:
        assert db.execute('SELECT attempts FROM jobs').fetchone()[0] == 1
