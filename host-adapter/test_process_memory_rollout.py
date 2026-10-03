import pytest
from lib.process_memory import ProcessMemoryStore
from test_process_memory_governance import verified_episode


def test_canary_isolated_from_default_search_and_rollback_preserves_history(tmp_path):
    store = ProcessMemoryStore(tmp_path / 'records.json')
    record = verified_episode(store)
    store.set_rollout(record['process_memory_id'], 'canary', experiment_id='exp-1')
    assert store.search('repair') == []
    assert len(store.search('repair', experiment_id='exp-1')) == 1
    assert store.search('repair', experiment_id='exp-2') == []
    store.set_rollout(record['process_memory_id'], 'rollback', reason='negative_transfer')
    assert store.search('repair', experiment_id='exp-1') == []
    history = next(r for r in store.all() if r['process_memory_id'] == record['process_memory_id'])['rollout_history']
    assert [e['action'] for e in history] == ['canary', 'rollback']
    assert history[-1]['reason'] == 'negative_transfer'


def test_canary_publication_requires_independently_verified_pairs(tmp_path):
    store = ProcessMemoryStore(tmp_path / 'records.json')
    record = verified_episode(store)
    store.set_rollout(record['process_memory_id'], 'canary', experiment_id='exp')
    with pytest.raises(ValueError, match='rollout_evaluation_required'):
        store.set_rollout(record['process_memory_id'], 'publish')
    with pytest.raises(ValueError, match='rollout_experiment_required'):
        store.set_rollout(record['process_memory_id'], 'canary')
