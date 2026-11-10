import pytest

from ham.adapter import event_from_hook
from ham.storage import IdempotencyConflict


@pytest.fixture(autouse=True)
def isolated_capture(tmp_path, monkeypatch):
    monkeypatch.setenv('HAM_CAPTURE_STATE_DIR', str(tmp_path))


def capture(prompt='one', **kwargs):
    return event_from_hook('UserPromptSubmit', {'session_id': 's', 'turn_id': 't', 'prompt': prompt}, **kwargs)


def test_distinct_steering_messages_share_turn_not_occurrence():
    assert capture()['event_id'] != capture('two')['event_id']


def test_identical_words_without_message_identity_are_not_a_retry():
    assert capture()['event_id'] != capture()['event_id']


def test_local_invocation_retry_is_stable_without_mutating_host_payload():
    a = capture(occurrence_id='local-1')
    assert a == capture(occurrence_id='local-1')
    assert a['provenance']['retry_identity'] == 'local_hook_invocation'
    assert a['provenance']['hook_invocation_id'] == 'local-1'
    assert 'hook_invocation_id' not in a['source_payload']
    with pytest.raises(IdempotencyConflict):
        capture('two', occurrence_id='local-1')


def test_host_message_identity_deduplicates_only_its_retry():
    source = {'session_id': 's', 'turn_id': 't', 'message_id': 'm1', 'prompt': 'one'}
    a = event_from_hook('UserPromptSubmit', source)
    assert a == event_from_hook('UserPromptSubmit', source)
    assert a['event_id'] != event_from_hook('UserPromptSubmit', dict(source, message_id='m2'))['event_id']
