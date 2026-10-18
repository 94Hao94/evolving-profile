import json
import sqlite3

import pytest

from repository import GuidanceRepository
from test_observation_task_scope import source
from test_source_authority_publication import _candidate
from observation_publish import build_observation_proposal
import publisher


def repo_with_broad_legacy(tmp_path):
    repo = GuidanceRepository(tmp_path / 'guidance.sqlite', 'bank')
    proposal = build_observation_proposal(_candidate(), [source('a', '本讲座保留核心论点。', 'a'),
        source('b', '本讲座补足提问三层。', 'b')], 'bank')
    proposal.update(id='legacy-unit', revision='original-revision', nature='inferred_pattern',
        scope_level='global', scope={'user_id': 'user', 'task_ids': [], 'project_ids': []}, support_count=2)
    repo.store_active_unit_for_migration(proposal)
    return repo


def test_scope_migration_dryrun_retains_evidence_and_makes_no_changes(tmp_path):
    repo = repo_with_broad_legacy(tmp_path)
    before = repo.active_units()
    result = publisher.hold_overbroad_observation(repo, 'legacy-unit', expected_unit_revision='original-revision',
        expected_active_revision=repo.active_revision(), backup_path=tmp_path / 'backup.sqlite')
    assert result['status'] == 'dry_run'
    assert result['candidate']['nature'] == 'task_local'
    assert result['candidate']['scope']['session_ids'] == ['lecture-session']
    assert len(result['candidate']['evidence_refs']) == 2
    assert repo.active_units() == before
    assert not (tmp_path / 'backup.sqlite').exists()


def test_scope_hold_uses_backup_and_revision_cas_without_destroying_history(tmp_path):
    repo = repo_with_broad_legacy(tmp_path)
    previous_revision = repo.active_revision()
    with pytest.raises(publisher.PublicationError, match='revision_conflict'):
        publisher.hold_overbroad_observation(repo, 'legacy-unit', expected_unit_revision='wrong',
            expected_active_revision=repo.active_revision(), backup_path=tmp_path / 'wrong.sqlite', dry_run=False)
    assert not (tmp_path / 'wrong.sqlite').exists()
    result = publisher.hold_overbroad_observation(repo, 'legacy-unit', expected_unit_revision='original-revision',
        expected_active_revision=repo.active_revision(), backup_path=tmp_path / 'backup.sqlite', dry_run=False)
    assert result['status'] == 'held_for_scoped_review'
    assert repo.active_units()[0]['preference_audit']['state'] == 'needs_review'
    assert repo.active_units()[0]['revision'] == 'original-revision'
    assert repo.active_revision() != previous_revision
    with pytest.raises(publisher.PublicationError, match='revision_conflict'):
        publisher.hold_overbroad_observation(repo, 'legacy-unit', expected_unit_revision='original-revision',
            expected_active_revision=previous_revision, backup_path=tmp_path / 'stale.sqlite', dry_run=False)
    assert not (tmp_path / 'stale.sqlite').exists()
    with sqlite3.connect(tmp_path / 'backup.sqlite') as db:
        assert db.execute('SELECT count(*) FROM unit_audits').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM unit_revisions WHERE active=1').fetchone()[0] == 1


def test_mixed_schema_same_session_remains_eligible_for_scoped_hold_preview(tmp_path):
    repo = GuidanceRepository(tmp_path / 'guidance.sqlite', 'bank')
    proposal = build_observation_proposal(_candidate(), [
        source('a', '本讲座保留核心论点。', 'a', task_id='native-task'),
        source('b', '本讲座补足提问三层。', 'b')], 'bank')
    proposal.update(id='mixed-legacy', revision='r1', nature='inferred_pattern', scope_level='global',
        scope={'user_id': 'user'}, support_count=2)
    repo.store_active_unit_for_migration(proposal)
    plan = publisher.hold_overbroad_observation(repo, 'mixed-legacy', expected_unit_revision='r1',
        expected_active_revision=repo.active_revision(), backup_path=tmp_path / 'backup.sqlite')
    assert plan['status'] == 'dry_run'
    assert plan['candidate']['support_count'] == 1
    assert plan['candidate']['scope']['task_ids'] == ['native-task']
    assert len(plan['candidate']['evidence_refs']) == 2
