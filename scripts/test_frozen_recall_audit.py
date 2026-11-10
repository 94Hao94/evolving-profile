import importlib.util
from pathlib import Path


def load_audit():
    path = Path(__file__).with_name('ep51_frozen_recall_audit.py')
    spec = importlib.util.spec_from_file_location('frozen_recall_audit', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate_metrics_do_not_credit_injected_seeds_as_backend_retrieval():
    audit = load_audit()
    case = {'backend_ids': ['live'], 'expected_related_ids': ['live', 'seed'],
            'expected_rejected_ids': ['wrong']}
    assert audit.metrics(case, ['live', 'seed']) == {
        'backend_positive_found': 1, 'backend_positive_total': 2,
        'gate_positive_kept': 2, 'gate_positive_total': 2,
        'unrelated_or_denied_kept': [], 'missed_related': [],
    }


def test_changed_frozen_snapshot_is_rejected_before_replay():
    audit = load_audit()
    snapshot = {'schema': 'ep51.frozen-candidate-audit.v1', 'cases': [], 'chunks': {}}
    sealed = audit.seal(snapshot)
    assert audit.verify(sealed) is True
    sealed['cases'].append({'query': 'changed'})
    assert audit.verify(sealed) is False


def test_replay_refuses_changed_gate_even_when_data_snapshot_is_sealed(tmp_path):
    import pytest

    audit = load_audit()
    snapshot = audit.seal({'schema': 'ep51.frozen-candidate-audit.v1', 'cases': [], 'chunks': {},
                          'current_gate_sha256': 'not-the-current-code'})
    with pytest.raises(ValueError, match='frozen_current_gate_changed'):
        audit.replay(snapshot, tmp_path / 'unread-baseline.py')
