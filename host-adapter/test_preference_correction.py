import json
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'guidance'))
from repository import GuidanceRepository


def test_correction_creates_revision_preserves_evidence_and_rejects_stale(tmp_path):
    from lib.preference_correction import correct_preference
    repo = GuidanceRepository(tmp_path / 'registry.sqlite3', 'bank')
    repo.store_active_unit_for_migration({'id': 'u', 'revision': 'r1', 'text': 'original', 'primary_category': 'delivery', 'scope': {'user_id': 'user'}, 'evidence_refs': [{'quote': 'original source'}]})
    repo.set_unit_audit('u', 'r1', {'state': 'approved'})
    result = correct_preference(repo.path, {'unit_id': 'u', 'expected_revision': 'r1', 'text': 'corrected', 'applies_when': ['documents'], 'exceptions': [], 'reason': 'scope correction'})
    assert result['applied']
    active = repo.active_units()[0]
    assert active['text'] == 'corrected'
    assert active['evidence_refs'] == [{'quote': 'original source'}]
    assert active['preference_audit']['state'] == 'approved'
    assert len(repo.unit_history('u')) == 2
    with pytest.raises(ValueError, match='revision_conflict'):
        correct_preference(repo.path, {'unit_id': 'u', 'expected_revision': 'r1', 'text': 'stale'})


def test_correction_does_not_promote_pending_or_edit_provenance(tmp_path):
    from lib.preference_correction import correct_preference
    repo = GuidanceRepository(tmp_path / 'registry.sqlite3', 'bank')
    repo.store_active_unit_for_migration({'id': 'u', 'revision': 'r1', 'text': 'original', 'primary_category': 'delivery'})
    repo.set_unit_audit('u', 'r1', {'state': 'needs_review'})
    correct_preference(repo.path, {'unit_id': 'u', 'expected_revision': 'r1', 'text': 'corrected'})
    assert repo.active_units()[0]['preference_audit']['state'] == 'needs_review'
    with pytest.raises(ValueError, match='unsupported_field'):
        correct_preference(repo.path, {'unit_id': 'u', 'expected_revision': 'r1', 'text': 'x', 'evidence_refs': []})
