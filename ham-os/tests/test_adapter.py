from ham.adapter import event_from_hook
import pytest

@pytest.fixture(autouse=True)
def isolated_capture(tmp_path, monkeypatch):
 monkeypatch.setenv('HAM_CAPTURE_STATE_DIR',str(tmp_path))

def test_hook_envelope_is_stable_and_source_isolated():
 h={'session_id':'s','cwd':'/p','prompt':'do it','message_id':'m'}; a=event_from_hook('UserPromptSubmit',h,'user_request'); b=event_from_hook('UserPromptSubmit',h,'user_request'); assert a['event_id']==b['event_id'] and a['idempotency_key']==b['idempotency_key'] and a['origin_class']=='user_request'
def test_ambient_is_not_user_statement(): assert event_from_hook('SessionStart',{'session_id':'s'},'ambient_context')['origin_class']=='ambient_context'
