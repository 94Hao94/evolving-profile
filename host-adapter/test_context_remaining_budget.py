"""Explicit recovery must spend only the existing three-attempt budget."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib.context_incremental import ContextIncremental, reassess_source_jobs
from lib.context_summary import read_context_index, update_context_index
from test_context_incremental import rollout, write_runtime_settings


def waiting_job(tmp_path, *, attempts=1):
    sid = '01a123a0-aa87-7cf2-a2bf-a1b8c969c3f7'
    root = tmp_path / 'sessions'
    source_path = rollout(root, sid)
    worker = ContextIncremental(tmp_path / 'state', root, bank_id='bank-a')
    write_runtime_settings(worker.root.parent)
    worker.discover(now=100)
    with worker.db() as db:
        db.execute("UPDATE jobs SET status='waiting_source',error_code='scenario_over_budget',attempts=?,input_revision='legacy-incomparable'", (attempts,))
    return worker, sid, source_path


def job(worker):
    with worker.db() as db:
        return dict(db.execute('SELECT * FROM jobs').fetchone())


def plan(worker, sid, **kwargs):
    return reassess_source_jobs(worker.root.parent, worker.session_root,
                               session_ids=[sid], resume_remaining_budget=True, **kwargs)


def apply(worker, sid, reviewed):
    return plan(worker, sid, apply=True, expected_plan_sha256=reviewed['plan_sha256'])


def test_explicit_recovery_retains_spent_budget_and_claims_next_attempt(tmp_path):
    worker, sid, _ = waiting_job(tmp_path)
    original = job(worker)
    index = read_context_index(worker.index)['sessions'][0]
    before = {p.name: p.read_bytes() for p in worker.root.iterdir() if p.is_file()}
    reviewed = plan(worker, sid)
    assert reviewed['model_calls'] == 0
    assert reviewed['changes'][0]['action'] == 'resume_remaining_budget'
    assert reviewed['observations'][0]['remaining_attempts'] == 2
    assert before == {p.name: p.read_bytes() for p in worker.root.iterdir() if p.is_file()}
    assert apply(worker, sid, reviewed)['applied'] == 1
    resumed = job(worker)
    assert resumed['status'] == 'pending'
    assert resumed['attempts'] == 1
    assert resumed['error_code'] == 'scenario_over_budget'
    assert resumed['source_check_pending'] == 0
    assert resumed['prior_status'] is None
    assert json.loads(resumed['input_qualification'])['input_revision_scheme'] == 'semantic-source-budget.v1'
    with worker.db() as db:
        evidence = json.loads(db.execute('SELECT evidence FROM job_evidence').fetchone()[0])
    assert evidence['kind'] == 'remaining_budget_source_reassessment'
    assert evidence['prior_job'] == original
    assert evidence['prior_index_row'] == index
    claimed = worker.claim(now=200)
    assert claimed['attempts'] == 2
    from lib.scenario_source import read_session_source
    assert worker.prepare_input(claimed, read_session_source(sid, worker.session_root), index) is None
    assert job(worker)['attempts'] == 2


def test_default_reassessment_still_does_not_requeue_eligible_waiting_job(tmp_path):
    worker, sid, _ = waiting_job(tmp_path)
    assert reassess_source_jobs(worker.root.parent, worker.session_root, session_ids=[sid])['changes'] == []
    reviewed = plan(worker, sid)
    with pytest.raises(ValueError, match='reassessment_stale_plan'):
        reassess_source_jobs(worker.root.parent, worker.session_root, session_ids=[sid], apply=True,
                            expected_plan_sha256=reviewed['plan_sha256'])
    assert job(worker)['status'] == 'waiting_source'


@pytest.mark.parametrize('scope', [None, [], ['01a123a0-aa87-7cf2-a2bf-a1b8c969c3f7'] * 33])
def test_resume_needs_explicit_bounded_scope_even_for_dry_run(tmp_path, scope):
    worker, _, _ = waiting_job(tmp_path)
    # Repeated IDs do not enlarge exact scope; use distinct IDs for the bound.
    if scope and len(scope) == 33:
        import uuid
        scope = [str(uuid.UUID(int=i)) for i in range(33)]
    with pytest.raises(ValueError, match='reassessment_explicit_scope'):
        reassess_source_jobs(worker.root.parent, worker.session_root,
                            session_ids=scope, resume_remaining_budget=True)


@pytest.mark.parametrize('status,attempts', [
    ('failed', 1), ('failed', 3), ('waiting_source', 3), ('protected', 1),
    ('complete', 1), ('source_not_applicable', 1), ('running', 1), ('pending', 1),
])
def test_resume_never_requeues_ineligible_status_or_exhausted_budget(tmp_path, status, attempts):
    worker, sid, _ = waiting_job(tmp_path, attempts=attempts)
    with worker.db() as db:
        db.execute('UPDATE jobs SET status=?', (status,))
    assert plan(worker, sid)['changes'] == []
    assert job(worker)['status'] == status


@pytest.mark.parametrize('mutation', ['no_bank', 'wrong_project', 'wrong_header', 'wrong_raw_paths', 'empty', 'protected', 'coverage_budget'])
def test_resume_requires_source_scope_permission_and_available_input_budget(tmp_path, mutation):
    worker, sid, path = waiting_job(tmp_path)
    if mutation in {'no_bank', 'wrong_project', 'wrong_raw_paths'}:
        def mutate(index):
            row = index['sessions'][0]
            if mutation == 'no_bank': row.pop('bank_id')
            elif mutation == 'wrong_project': row['project_key'] = 'wrong-project'
            else: row['raw_source_files'] = ['/some/other/source']
            return index
        update_context_index(worker.index, mutate)
    elif mutation == 'wrong_header':
        rollout(path.parent, sid, cwd='/another/project')
    elif mutation == 'empty':
        path.write_text(path.read_text().splitlines()[0] + '\n')
    elif mutation == 'protected':
        rollout(path.parent, sid, text='不要写入记忆。')
    else:
        # <60000 source characters, >120000 mandatory transport characters.
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[-1]['payload']['content'][0]['text'] = '\x01' * 30000
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    reviewed = plan(worker, sid)
    assert not any(c.get('action') == 'resume_remaining_budget' for c in reviewed['changes'])
    assert job(worker)['attempts'] == 1


@pytest.mark.parametrize('mutation', ['job', 'source', 'index', 'permission'])
def test_resume_rejects_mutated_reviewed_plan_without_requeue(tmp_path, mutation):
    worker, sid, path = waiting_job(tmp_path)
    reviewed = plan(worker, sid)
    if mutation == 'job':
        with worker.db() as db: db.execute('UPDATE jobs SET attempts=2')
    elif mutation == 'source':
        rollout(path.parent, sid, text='A different semantic request')
    elif mutation == 'index':
        def mutate(index):
            index['sessions'][0]['bank_id'] = 'bank-b'
            return index
        update_context_index(worker.index, mutate)
    else:
        write_runtime_settings(worker.root.parent, {'generation':2})
    with pytest.raises(ValueError, match='reassessment_'):
        apply(worker, sid, reviewed)
    assert job(worker)['status'] == 'waiting_source'


def test_resume_third_attempt_is_last_and_repeat_apply_is_stale(tmp_path):
    worker, sid, _ = waiting_job(tmp_path, attempts=2)
    reviewed = plan(worker, sid)
    apply(worker, sid, reviewed)
    with pytest.raises(ValueError, match='reassessment_stale_plan'):
        apply(worker, sid, reviewed)
    result = worker.run_once({}, now=200, processor=lambda *_: (_ for _ in ()).throw(ValueError('scenario_state_invalid')))
    assert result['status'] == 'failed'
    assert job(worker)['attempts'] == 3
    assert worker.claim(now=10000) is None


@pytest.mark.parametrize('mutation', ['source', 'permission', 'missing_index_row'])
def test_resume_commit_races_roll_back_job_and_evidence(tmp_path, monkeypatch, mutation):
    import lib.context_incremental as module
    worker, sid, path = waiting_job(tmp_path)
    reviewed = plan(worker, sid)
    before_job, before_index = job(worker), worker.index.read_bytes()
    update = module.update_context_index
    def race(index_path, updater):
        if mutation == 'source':
            rollout(path.parent, sid, text='不要写入记忆。')
        elif mutation == 'permission':
            write_runtime_settings(worker.root.parent, {'modules':{'scenario_summary':{'record':False}}})
        def concurrent_index(index):
            if mutation == 'missing_index_row':
                index['sessions'] = []
            return updater(index)
        return update(index_path, concurrent_index)
    monkeypatch.setattr(module, 'update_context_index', race)
    with pytest.raises(ValueError, match='reassessment_'):
        apply(worker, sid, reviewed)
    assert job(worker) == before_job
    assert worker.index.read_bytes() == before_index
    with worker.db() as db:
        assert db.execute('SELECT count(*) FROM job_evidence').fetchone()[0] == 0


def test_cli_resume_plan_needs_no_provider_and_does_not_apply(tmp_path):
    worker, sid, _ = waiting_job(tmp_path)
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('context-incremental-worker.py')),
        '--state-root', str(worker.root.parent), '--session-root', str(worker.session_root),
        '--reassess-source', '--resume-remaining-budget', '--session-id', sid], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['changes'][0]['action'] == 'resume_remaining_budget'
    assert job(worker)['status'] == 'waiting_source'


def test_readonly_plan_can_read_closed_wal_database_without_mutating_production(tmp_path):
    import sqlite3
    state = tmp_path / 'state'
    context = state / 'context'
    context.mkdir(parents=True)
    path = context / 'context-incremental.sqlite'
    db = sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE jobs(session_id TEXT)')
    db.execute("INSERT INTO jobs VALUES('unselected-session')")
    db.commit()
    db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    db.close()
    for suffix in ('-wal', '-shm'):
        Path(str(path) + suffix).unlink(missing_ok=True)
    before = {p.name:p.read_bytes() for p in context.iterdir()}
    result = reassess_source_jobs(state, tmp_path / 'sessions',
        session_ids=['01a123a0-aa87-7cf2-a2bf-a1b8c969c3f7'])
    assert result['observations'] == []
    assert before == {p.name:p.read_bytes() for p in context.iterdir()}
