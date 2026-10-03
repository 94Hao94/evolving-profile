"""PRD safety contracts: scope, evidence, drift, and low-intervention cold start."""
import pytest

from lib.process_memory import ProcessMemoryStore, compatibility_match, compute_intervention
from test_process_memory import base_trace


def verified_episode(store, **fields):
    trace = store.record_trajectory(base_trace(**fields))
    return store.promote_episode(trace['process_memory_id'], {
        'text': 'repair import failure',
        'verification_evidence': [{'verifier_kind': 'automated_test', 'status': 'passed', 'id': trace['process_memory_id']}],
    })


def test_unknown_verifier_cannot_promote(tmp_path):
    store = ProcessMemoryStore(tmp_path / 'records.json')
    trace = store.record_trajectory(base_trace())
    with pytest.raises(ValueError, match='verification_evidence_required'):
        store.promote_episode(trace['process_memory_id'], {'verification_evidence': [{'verifier_kind': 'made_up', 'status': 'passed'}]})


def test_pattern_preserves_model_environment_and_context(tmp_path):
    store = ProcessMemoryStore(tmp_path / 'records.json')
    episodes = [verified_episode(store, primary_context={'project_id': 'a'}, source_trace_ids=[str(i)]) for i in range(2)]
    pattern = store.promote_pattern([e['process_memory_id'] for e in episodes], {'text': 'repair'})
    assert pattern['model_profile']['family'] == 'model-a'
    assert pattern['environment_fingerprint']['toolchain'] == ['python']
    assert pattern['primary_context']['project_id'] == 'a'


def test_pattern_cannot_widen_scope_by_payload(tmp_path):
    store = ProcessMemoryStore(tmp_path / 'records.json')
    episodes = [verified_episode(store, source_trace_ids=[str(i)]) for i in range(2)]
    with pytest.raises(ValueError, match='process_memory_scope_widening'):
        store.promote_pattern([e['process_memory_id'] for e in episodes], {'model_profile': {'family': 'model-b'}})


def test_missing_requested_compatibility_is_unknown_not_match():
    assert not compatibility_match({'model_profile': {}, 'environment_fingerprint': {}}, {'model_family': 'model-a', 'toolchain': ['python']})


def test_cross_model_transfer_requires_verified_status():
    base = {'model_profile': {'family': 'model-a', 'version': '1'}, 'environment_fingerprint': {'toolchain': ['python']}, 'transfer_scope': {'model_family': 'model-b', 'transfer_status': 'candidate'}}
    assert not compatibility_match(base, {'model_family': 'model-b', 'model_version': '2', 'toolchain': ['python']})
    base['transfer_scope']['transfer_status'] = 'verified'
    assert compatibility_match(base, {'model_family': 'model-b', 'model_version': '2', 'toolchain': ['python']})
    base['transfer_scope']['transfer_status'] = 'blocked'
    assert not compatibility_match(base, {'model_family': 'model-b', 'model_version': '2', 'toolchain': ['python']})


def test_project_scope_and_drift_are_applied_before_candidates(tmp_path):
    store = ProcessMemoryStore(tmp_path / 'records.json')
    a = verified_episode(store, primary_context={'project_id': 'a'})
    verified_episode(store, primary_context={'project_id': 'b'})
    verified_episode(store, primary_context={'project_id': 'a'}, drift_status='revalidation_required')
    rows = store.search('repair', primary_context={'project_id': 'a'})
    assert [r['process_memory_id'] for r in rows] == [a['process_memory_id']]


def test_unknown_profile_is_hint_only():
    assert compute_intervention({'confidence': 'unknown', 'sample_count': 0}, {})['intervention_level'] == 'hint'


def test_model_upgrade_has_separate_capability_profile(tmp_path):
    store = ProcessMemoryStore(tmp_path / 'records.json')
    for _ in range(3):
        store.record_capability_observation({'model_family': 'a', 'model_version': '1', 'task_archetype': 'coding', 'phase': 'verify', 'outcome': 'success', 'verifier_kind': 'automated_test', 'status': 'passed'})
    assert store.capability_profile('a', 'coding', 'verify', model_version='2')['sample_count'] == 0
    profile = store.capability_profile('a', 'coding', 'verify', model_version='1')
    assert profile['sample_count'] == 3
    assert profile['confidence'] == 'unknown'
    assert 0 < profile['confidence_interval'][0] < profile['confidence_interval'][1] <= 1


def test_missing_sources_cannot_be_silently_ignored(tmp_path):
    store = ProcessMemoryStore(tmp_path / 'records.json')
    episodes = [verified_episode(store, source_trace_ids=[str(i)]) for i in range(2)]
    with pytest.raises(ValueError, match='process_memory_source_not_found'):
        store.promote_pattern([e['process_memory_id'] for e in episodes] + ['missing'], {})


def test_revalidation_status_is_reversible_only_with_independent_evidence(tmp_path):
    store = ProcessMemoryStore(tmp_path / 'records.json')
    episode = verified_episode(store)
    held = store.set_drift_status(episode['process_memory_id'], 'revalidation_required')
    assert held['drift_status'] == 'revalidation_required'
    with pytest.raises(ValueError, match='revalidation_evidence_required'):
        store.set_drift_status(episode['process_memory_id'], 'stable')
    restored = store.set_drift_status(episode['process_memory_id'], 'stable', [{'verifier_kind': 'automated_test', 'status': 'passed'}])
    assert restored['drift_status'] == 'stable'
