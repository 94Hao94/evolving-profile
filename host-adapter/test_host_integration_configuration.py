import json
from pathlib import Path
import pytest

PROFILE={'id':'workbuddy','config':{'format':'json','apply':True}}
DESIRED={'command':'/absolute/python','args':['/absolute/ep.py'],'env':{}}


def test_preview_never_writes_and_unrelated_servers_and_hooks_preserved(tmp_path):
    from lib.host_integration.configuration import plan_configuration,apply_configuration
    p=tmp_path/'mcp.json';original={'mcpServers':{'other':{'env':{'API_KEY':'credential-marker-must-not-leak'}}},'hooks':{'Stop':['owned-by-user']}}
    p.write_text(json.dumps(original));before=p.read_bytes()
    plan=plan_configuration(PROFILE,p,DESIRED)
    assert p.read_bytes()==before
    assert 'credential-marker-must-not-leak' not in str(plan)
    result=apply_configuration(plan,expected_sha256=plan['before_sha256'])
    actual=json.loads(p.read_text())
    assert actual['mcpServers']['other']==original['mcpServers']['other']
    assert actual['hooks']==original['hooks']
    assert actual['mcpServers']['evolving_profile_controller']['command']=='/absolute/python'
    assert result['after_sha256']!=result['before_sha256']


def test_changed_since_preview_rejected(tmp_path):
    from lib.host_integration.configuration import plan_configuration,apply_configuration
    p=tmp_path/'mcp.json';p.write_text('{}');plan=plan_configuration(PROFILE,p,DESIRED)
    p.write_text('{"later":true}')
    with pytest.raises(ValueError,match='revision_conflict'):apply_configuration(plan,expected_sha256=plan['before_sha256'])
    assert json.loads(p.read_text())=={'later':True}


def test_rollback_preserves_later_user_edit(tmp_path):
    from lib.host_integration.configuration import plan_configuration,apply_configuration,rollback_configuration
    p=tmp_path/'mcp.json';plan=plan_configuration(PROFILE,p,DESIRED)
    receipt=apply_configuration(plan,expected_sha256=None)
    p.write_text('{"user_edit":1}')
    with pytest.raises(ValueError,match='revision_conflict'):
        rollback_configuration(receipt,expected_sha256=receipt['after_sha256'])
    assert json.loads(p.read_text())=={'user_edit':1}


@pytest.mark.parametrize('text',['broken','{"mcpServers":{},"mcpServers":{}}','[]'])
def test_corrupt_or_duplicate_keys_rejected(tmp_path,text):
    from lib.host_integration.configuration import plan_configuration
    p=tmp_path/'mcp.json';p.write_text(text)
    with pytest.raises(ValueError):plan_configuration(PROFILE,p,DESIRED)
    assert p.read_text()==text


def test_symlink_target_not_followed(tmp_path):
    from lib.host_integration.configuration import plan_configuration
    p=tmp_path/'real';p.write_text('{}');link=tmp_path/'link'
    try:link.symlink_to(p)
    except OSError:pytest.skip('symlink unavailable')
    with pytest.raises(ValueError):plan_configuration(PROFILE,link,DESIRED)


def test_wrong_owner_cannot_replace_entry(tmp_path):
    from lib.host_integration.configuration import plan_configuration
    p=tmp_path/'mcp.json';p.write_text(json.dumps({'mcpServers':{'evolving_profile_controller':{'command':'user-owned'}}}))
    with pytest.raises(ValueError,match='unowned'):plan_configuration(PROFILE,p,DESIRED)


def test_safe_apply_and_rollback(tmp_path):
    from lib.host_integration.configuration import plan_configuration,apply_configuration,rollback_configuration
    p=tmp_path/'mcp.json';p.write_text('{"keep":1}\n');before=p.read_bytes()
    plan=plan_configuration(PROFILE,p,DESIRED);r=apply_configuration(plan,expected_sha256=plan['before_sha256'])
    rollback_configuration(r,expected_sha256=r['after_sha256'])
    assert p.read_bytes()==before


def test_unsupported_format_is_import_only_and_credentials_not_in_preview(tmp_path):
    from lib.host_integration.configuration import plan_configuration,apply_configuration
    p=tmp_path/'config.toml';p.write_text('# important comment\n')
    plan=plan_configuration({'id':'codex','config':{'format':'toml','apply':False}},p,DESIRED)
    assert plan['apply_supported'] is False
    with pytest.raises(ValueError):apply_configuration(plan,expected_sha256=plan['before_sha256'])
    with pytest.raises(ValueError):plan_configuration(PROFILE,tmp_path/'x',{'env':{'API_KEY':'do-not-leak'}})


def test_windows_absolute_executable_can_be_prepared_on_mac(tmp_path):
    from lib.host_integration.configuration import plan_configuration
    desired={'command':r'C:\Program Files\Python\python.exe','args':[r'C:\EP\host.py'],'env':{}}
    result=plan_configuration(PROFILE,tmp_path/'mcp.json',desired)
    assert result['desired']['command']==r'C:\Program Files\Python\python.exe'


@pytest.mark.parametrize('env',['not-an-object',[],{'BAD':7}])
def test_malformed_environment_returns_actionable_error_without_write(tmp_path,env):
    from lib.host_integration.configuration import plan_configuration
    p=tmp_path/'mcp.json';p.write_text('{}')
    with pytest.raises(ValueError,match='invalid_desired_environment'):
        plan_configuration(PROFILE,p,{**DESIRED,'env':env})
    assert p.read_text()=='{}'


def test_cross_platform_absolute_path_preparation_is_symmetric(monkeypatch):
    from lib.host_integration import configuration
    from pathlib import PureWindowsPath
    monkeypatch.setattr(configuration,'Path',PureWindowsPath)
    configuration._validate_desired({'command':'/absolute/python','args':[],'env':{}})
