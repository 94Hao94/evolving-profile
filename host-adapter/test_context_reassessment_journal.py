"""Recovery across the real JSON replacement and SQLite commit boundaries."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import lib.context_incremental as module
from lib.context_summary import read_context_index, update_context_index
from test_context_remaining_budget import waiting_job, job, plan, apply


JOURNAL = 'context-reassessment-journal.json'


def target_row(worker):
    return read_context_index(worker.index)['sessions'][0]


def crash_apply(worker, sid, reviewed, stage='after_index'):
    code = '''
import os, sys
import lib.context_incremental as module
import lib.context_summary as summary
stage = sys.argv[5]
if stage == 'before_index':
    def crash(*args, **kwargs): os._exit(97)
    summary.write_context_index = crash
elif stage == 'after_commit':
    import lib.context_reassessment_journal as journal
    def crash(*args, **kwargs): os._exit(97)
    journal._remove_journal = crash
else:
    real_update = module.update_context_index
    def crash(index_path, updater):
        real_update(index_path, updater)
        os._exit(97)
    module.update_context_index = crash
module.reassess_source_jobs(sys.argv[1], sys.argv[2], session_ids=[sys.argv[3]],
    resume_remaining_budget=True, apply=True, expected_plan_sha256=sys.argv[4])
'''
    env = {**os.environ, 'PYTHONPATH':str(Path(__file__).parent)}
    result = subprocess.run([sys.executable, '-c', code, str(worker.root.parent),
        str(worker.session_root), sid, reviewed['plan_sha256'], stage], env=env, capture_output=True, text=True)
    assert result.returncode == 97, result.stderr


def test_exception_after_actual_index_replace_compensates_target_and_budget(tmp_path, monkeypatch):
    worker, sid, _ = waiting_job(tmp_path)
    reviewed = plan(worker, sid)
    old_job, old_row = job(worker), target_row(worker)
    real_update = module.update_context_index
    def fail_after_write(index_path, updater):
        real_update(index_path, updater)
        raise OSError('simulated_failure_after_atomic_index_replace')
    monkeypatch.setattr(module, 'update_context_index', fail_after_write)
    with pytest.raises(OSError, match='simulated_failure'):
        apply(worker, sid, reviewed)
    assert job(worker) == old_job
    assert target_row(worker) == old_row
    assert not (worker.root / JOURNAL).exists()
    with worker.db() as db:
        assert db.execute('SELECT count(*) FROM job_evidence').fetchone()[0] == 0


@pytest.mark.parametrize('stage', ['before_index', 'after_index', 'after_commit'])
def test_process_crash_recovery_is_idempotent_and_never_resets_attempts(tmp_path, stage):
    worker, sid, _ = waiting_job(tmp_path)
    reviewed = plan(worker, sid)
    old_job, old_row = job(worker), target_row(worker)
    crash_apply(worker, sid, reviewed, stage)
    assert (worker.root / JOURNAL).is_file()
    recovered = module.ContextIncremental(worker.root.parent, worker.session_root)
    if stage == 'after_commit':
        assert job(recovered)['status'] == 'pending'
        assert target_row(recovered)['status'] == 'raw_available_summary_pending'
        assert job(recovered)['attempts'] == 1
        assert recovered.claim(now=200)['attempts'] == 2
    else:
        assert job(recovered) == old_job
        assert target_row(recovered) == old_row
        assert recovered.claim(now=200) is None
    assert not (worker.root / JOURNAL).exists()
    again = module.ContextIncremental(worker.root.parent, worker.session_root)
    assert job(again) == job(recovered)
    assert target_row(again) == target_row(recovered)


def test_readonly_plan_with_pending_recovery_refuses_without_any_writes(tmp_path):
    worker, sid, _ = waiting_job(tmp_path)
    reviewed = plan(worker, sid)
    crash_apply(worker, sid, reviewed)
    before = {p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in worker.root.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match='reassessment_recovery_required'):
        plan(worker, sid)
    assert before == {p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in worker.root.iterdir() if p.is_file()}


@pytest.mark.parametrize('entry', ['constructor', 'claim', 'discover'])
@pytest.mark.parametrize('conflict', ['job', 'index'])
def test_foreign_changes_fail_closed_and_keep_recovery_journal(tmp_path, entry, conflict):
    worker, sid, _ = waiting_job(tmp_path)
    reviewed = plan(worker, sid)
    crash_apply(worker, sid, reviewed)
    if conflict == 'job':
        with worker.db() as db: db.execute('UPDATE jobs SET attempts=2')
    else:
        def change(index):
            index['sessions'][0]['bank_id'] = 'foreign-bank'
            return index
        update_context_index(worker.index, change)
    before_job, before_index = job(worker), worker.index.read_bytes()
    with pytest.raises(ValueError, match='reassessment_recovery_conflict'):
        if entry == 'constructor':
            module.ContextIncremental(worker.root.parent, worker.session_root)
        elif entry == 'claim': worker.claim(now=200)
        else: worker.discover(now=300)
    assert job(worker) == before_job
    assert worker.index.read_bytes() == before_index
    assert (worker.root / JOURNAL).exists()


def test_compensation_preserves_unrelated_index_rows_and_metadata(tmp_path):
    worker, sid, _ = waiting_job(tmp_path)
    old_row = target_row(worker)
    crash_apply(worker, sid, plan(worker, sid))
    def add_other(index):
        index['sessions'].append({'session_id':'other', 'status':'foreign-status'})
        index['foreign_metadata'] = {'keep':True}
        return index
    update_context_index(worker.index, add_other)
    module.ContextIncremental(worker.root.parent, worker.session_root)
    index = read_context_index(worker.index)
    assert index['sessions'][0] == old_row
    assert index['sessions'][1] == {'session_id':'other', 'status':'foreign-status'}
    assert index['foreign_metadata'] == {'keep':True}


@pytest.mark.parametrize('bad', ['corrupt', 'oversized', 'symlink'])
def test_unsafe_journal_blocks_worker_without_touching_other_files(tmp_path, bad):
    worker, _, _ = waiting_job(tmp_path)
    path = worker.root / JOURNAL
    external = tmp_path / 'external'
    external.write_text('outside')
    if bad == 'symlink': path.symlink_to(external)
    elif bad == 'oversized':
        with path.open('wb') as stream: stream.truncate(16 * 1024 * 1024 + 1)
    else: path.write_text('{broken')
    before_job, before_index = job(worker), worker.index.read_bytes()
    with pytest.raises(ValueError, match='reassessment_recovery_'):
        worker.claim(now=200)
    assert job(worker) == before_job
    assert worker.index.read_bytes() == before_index
    assert external.read_text() == 'outside'


def test_resume_option_does_not_mix_default_reclassification_actions(tmp_path):
    worker, sid, path = waiting_job(tmp_path)
    rows = path.read_text().splitlines()
    message = json.loads(rows[-1])
    message['payload']['role'] = 'assistant'
    message['payload']['phase'] = 'final_answer'
    rows[-1] = json.dumps(message)
    path.write_text('\n'.join(rows) + '\n')
    with worker.db() as db: db.execute("UPDATE jobs SET status='failed'")
    reviewed = plan(worker, sid)
    assert reviewed['changes'] == []


def test_old_identical_plan_evidence_is_not_this_operation_commit_marker(tmp_path):
    worker, sid, _ = waiting_job(tmp_path)
    old_job, old_row = job(worker), target_row(worker)
    first = plan(worker, sid)
    apply(worker, sid, first)
    # An operator restores original rows but retains the audit evidence. A
    # second operation must not confuse that older commit with its own commit.
    with worker.db() as db:
        columns = list(old_job)
        db.execute('UPDATE jobs SET ' + ','.join(k+'=?' for k in columns),
                   [old_job[k] for k in columns])
    def restore(index):
        index['sessions'][0] = old_row
        return index
    update_context_index(worker.index, restore)
    second = plan(worker, sid)
    assert second['plan_sha256'] == first['plan_sha256']
    crash_apply(worker, sid, second)
    module.ContextIncremental(worker.root.parent, worker.session_root)
    assert job(worker) == old_job
    assert target_row(worker) == old_row


@pytest.mark.parametrize('name', ['context-index.json', 'context-incremental.sqlite'])
def test_pending_recovery_rejects_symlink_before_creating_external_locks(tmp_path, name):
    worker, sid, _ = waiting_job(tmp_path)
    crash_apply(worker, sid, plan(worker, sid))
    outside = tmp_path / 'outside'
    outside.mkdir()
    original = worker.root / name
    moved = outside / name
    original.rename(moved)
    original.symlink_to(moved)
    before = {p.name:p.read_bytes() for p in outside.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match='reassessment_recovery_unsafe_path'):
        worker.claim(now=200)
    assert before == {p.name:p.read_bytes() for p in outside.iterdir() if p.is_file()}


def test_plan_detects_recovery_started_after_initial_pending_check(tmp_path, monkeypatch):
    worker, sid, _ = waiting_job(tmp_path)
    build = module._reassessment_plan
    def race(*args, **kwargs):
        result = build(*args, **kwargs)
        (worker.root / JOURNAL).write_text('{concurrent-operation')
        return result
    monkeypatch.setattr(module, '_reassessment_plan', race)
    with pytest.raises(ValueError, match='reassessment_recovery_required'):
        plan(worker, sid)


def test_cleanup_error_after_commit_never_reverts_committed_work(tmp_path, monkeypatch):
    from lib import context_reassessment_journal as journal
    worker, sid, _ = waiting_job(tmp_path)
    reviewed = plan(worker, sid)
    remove = journal._remove_journal
    calls = []
    def fail_once(root):
        calls.append(root)
        if len(calls) == 1: raise OSError('cleanup_after_commit')
        return remove(root)
    monkeypatch.setattr(journal, '_remove_journal', fail_once)
    with pytest.raises(OSError, match='cleanup_after_commit'):
        apply(worker, sid, reviewed)
    assert job(worker)['status'] == 'pending'
    assert job(worker)['attempts'] == 1
    assert target_row(worker)['status'] == 'raw_available_summary_pending'
    assert not (worker.root / JOURNAL).exists()
    with worker.db() as db:
        assert db.execute('SELECT count(*) FROM job_evidence').fetchone()[0] == 1
