import datetime
import json
import pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'guidance'))


def test_same_session_and_prompt_across_hosts_never_join():
    from lib.host_integration.identity import bind_host_identity
    claim={'session_id':'same','turn_id':'turn','prompt':'same'}
    a=bind_host_identity(claim,{'owner_id':'owner','host_id':'workbuddy','installation_id':'one','trusted':True})
    b=bind_host_identity(claim,{'owner_id':'owner','host_id':'doubao_work','installation_id':'two','trusted':True})
    assert a['binding_key']!=b['binding_key']
    assert a['host_id']=='workbuddy'


def test_missing_native_id_is_adapter_assigned():
    from lib.host_integration.identity import bind_host_identity
    a=bind_host_identity({}, {})
    assert a['identity_origin']=='adapter_assigned'
    assert a['attestation']=='unattested'
    assert a['usable_for_capture'] is False


def test_same_person_different_org_is_not_auto_authorized():
    from lib.host_integration.identity import bind_host_identity,validate_binding
    a=bind_host_identity({'session_id':'s'},{'owner_id':'personal','host_id':'workbuddy','installation_id':'x','trusted':True})
    with pytest.raises(PermissionError):validate_binding(a,{'owner_id':'company','host_id':'workbuddy','installation_id':'x'})


def test_codex_legacy_receipt_unchanged():
    from host_contract import bind_occurrence
    result=bind_occurrence({'message_id':'m','host_id':'codex','session_id':'s','turn_id':'t','prompt':'p'})
    assert result['occurrence_id']=='m'
    assert result['identity_origin']=='host'


def test_unattested_claim_cannot_use_latest_codex_prompt(tmp_path,monkeypatch):
    from context_binding import resolve_prompt_binding
    root=tmp_path/'.evolving-profile/audit';root.mkdir(parents=True)
    (root/'prompt-ingress.jsonl').write_text(json.dumps({'hook_invocation_id':'check','session_id':'s',
        'turn_id':'t','at':'2026-10-18T00:00:00Z','host_id':'codex'})+'\n')
    monkeypatch.setenv('EVOLVING_PROFILE_HOST_ID','doubao_work')
    monkeypatch.delenv('EVOLVING_PROFILE_INSTALLATION_ID',raising=False)
    result=resolve_prompt_binding('check','2026-10-18T01:00:00Z',tmp_path)
    assert result['state']!='prompt_bound'


def test_native_non_codex_binding_is_namespaced(tmp_path,monkeypatch):
    from context_binding import resolve_prompt_binding
    root=tmp_path/'.evolving-profile/audit';root.mkdir(parents=True)
    rows=[{'hook_invocation_id':'c','session_id':'same','turn_id':'t','at':'2026-10-18T00:00:00Z',
           'host_id':'workbuddy','installation_id':'one','owner_id':'owner'},
          {'hook_invocation_id':'other','session_id':'same','turn_id':'z','at':'2026-10-18T00:30:00Z','host_id':'codex'}]
    (root/'prompt-ingress.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    monkeypatch.setenv('EVOLVING_PROFILE_HOST_ID','workbuddy')
    monkeypatch.setenv('EVOLVING_PROFILE_INSTALLATION_ID','one')
    monkeypatch.setenv('EVOLVING_PROFILE_OWNER_ID','owner')
    result=resolve_prompt_binding('c','2026-10-18T01:00:00Z',tmp_path)
    assert result['state']=='prompt_bound'
    assert result['host_id']=='workbuddy'
