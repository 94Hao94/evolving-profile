import pytest


def test_duplicate_message_text_does_not_deduplicate_distinct_events():
    from lib.host_integration.events import normalize_event
    binding={'host_id':'workbuddy','installation_id':'i','session_id':'s','turn_id':'t','binding_key':'key','attestation':'trusted_entry','usable_for_capture':True}
    a=normalize_event({'hook_event_name':'UserPromptSubmit','message_id':'one','prompt':'same'},{'id':'workbuddy'},binding)
    b=normalize_event({'hook_event_name':'UserPromptSubmit','message_id':'two','prompt':'same'},{'id':'workbuddy'},binding)
    assert a['event_key']!=b['event_key']
    assert a['kind']=='prompt_submitted'


def test_untrusted_or_unknown_event_never_captures():
    from lib.host_integration.events import normalize_event
    a=normalize_event({'hook_event_name':'FutureEvent'},{'id':'doubao_work'},{'host_id':'doubao_work'})
    assert a['capture_allowed'] is False and a['status']=='unknown_event'


def test_cancelled_event_is_not_task_success_and_no_implicit_authorization():
    from lib.host_integration.events import normalize_event
    a=normalize_event({'hook_event_name':'Stop','cancelled':True},{'id':'workbuddy'},
        {'host_id':'workbuddy','binding_key':'k','usable_for_capture':True,'attestation':'trusted_entry'})
    assert a['outcome']=='cancelled'
    assert a['capture_allowed'] is False


def test_event_cannot_self_authorize_capture():
    from lib.host_integration.events import normalize_event
    a=normalize_event({'hook_event_name':'Stop','capture_authorized':True,'source_verified':True},
        {'id':'workbuddy'}, {'host_id':'workbuddy','binding_key':'k','usable_for_capture':True,'attestation':'trusted_entry'})
    assert a['capture_allowed'] is False
