import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def registry():
    from lib.host_integration.registry import load_registry
    return load_registry(ROOT / 'config/host-integrations.v1.json')


def test_all_profiles_have_separate_capability_evidence():
    rows = registry()['profiles']
    assert {r['id'] for r in rows} == {'codex','claude_code_cli','claude_code_desktop_local',
        'claude_desktop_chat','hermes','workbuddy','doubao_work','generic_mcp'}
    assert all('macos' in r['platforms'] and 'windows' in r['platforms'] for r in rows)
    assert next(r for r in rows if r['id']=='doubao_work')['documented']['prompt_hook'] is None


def test_probe_never_proves_native_host():
    from lib.host_integration.readiness import readiness
    profile = next(r for r in registry()['profiles'] if r['id']=='workbuddy')
    context = {'host_version':'1','adapter_revision':'a','config_sha256':'c','mode':'local','platform':'macos'}
    observation = {**context,'capability_id':'mcp_stdio','evidence_kind':'isolated_probe',
        'state':'host_verified','observed_at':'2026-10-18T00:00:00Z','probe_id':'p'}
    result = readiness(profile,[observation],context)
    assert result['capabilities']['mcp_stdio']['state']=='protocol_verified'
    assert result['capabilities']['mcp_stdio']['evidence_kind']=='isolated_probe'


def test_version_change_expires_observation():
    from lib.host_integration.readiness import readiness
    profile = registry()['profiles'][0]
    context = {'host_version':'new','adapter_revision':'a','config_sha256':'c','mode':'local','platform':'macos'}
    observation = {**context,'host_version':'old','capability_id':'mcp_stdio',
        'evidence_kind':'native_host','state':'host_verified','probe_id':'p','observed_at':'2026-10-18T00:00:00Z'}
    result = readiness(profile,[observation],context)
    assert result['capabilities']['mcp_stdio']['state'] != 'host_verified'
    assert result['capabilities']['mcp_stdio']['stale'] is True


def test_missing_hook_is_unknown():
    from lib.host_integration.readiness import readiness
    profile = next(r for r in registry()['profiles'] if r['id']=='doubao_work')
    assert readiness(profile,[],{})['capabilities']['prompt_hook']['state']=='unknown'


def test_mode_and_platform_evidence_do_not_leak():
    from lib.host_integration.readiness import readiness
    profile = registry()['profiles'][0]
    context = {'host_version':'1','adapter_revision':'a','config_sha256':'c','mode':'wsl','platform':'windows'}
    observation = {**context,'platform':'macos','mode':'local','capability_id':'mcp_stdio',
        'evidence_kind':'native_host','state':'host_verified','probe_id':'p','observed_at':'2026-10-18T00:00:00Z'}
    result = readiness(profile,[observation],context)
    assert result['capabilities']['mcp_stdio']['state'] != 'host_verified'


def test_unknown_wire_and_untrusted_success_are_rejected(tmp_path):
    import json
    import pytest
    from lib.host_integration.registry import load_registry
    from lib.host_integration.readiness import readiness
    p=tmp_path/'r.json';p.write_text(json.dumps({'schema':'future','profiles':[]}))
    with pytest.raises(ValueError):load_registry(p)
    profile = registry()['profiles'][0]
    result=readiness(profile,[{'capability_id':'mcp_stdio','state':'host_verified'}],{})
    assert result['capabilities']['mcp_stdio']['state'] != 'host_verified'
