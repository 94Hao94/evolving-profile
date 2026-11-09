from pathlib import Path
import plistlib


def profile():
    return {'id':'sample','platforms':['macos','windows'],'documented':{},
        'apps':[],'executables':[],'config':{'paths':{'macos':[],'windows':[]}}}


def discover(p, tmp_path, **kwargs):
    from lib.host_integration.environment import discover_hosts
    return discover_hosts({'profiles':[p]}, {'platform':'macos','architecture':'arm64',
        'home':str(tmp_path),'search_roots':[],**kwargs}, {})['hosts'][0]


def test_mac_bundle_metadata_only(tmp_path):
    p=profile();app=tmp_path/'App.app';(app/'Contents').mkdir(parents=True)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'sample.app','CFBundleShortVersionString':'2'}))
    p['apps']=[{'path':str(app),'bundle_id':'sample.app'}]
    result=discover(p,tmp_path)
    assert result['installation']['state']=='detected'
    assert result['installation']['candidates'][0]['version']=='2'
    assert result['readiness']['host_verified'] is False


def test_windows_unicode_and_space_paths(tmp_path):
    p=profile();p['executables']=['sample'];folder=tmp_path/'中文 文件夹';folder.mkdir()
    (folder/'sample.exe').write_bytes(b'not executed')
    result=discover(p,tmp_path,platform='windows',search_roots=[str(folder)])
    assert result['installation']['state']=='detected'
    assert result['installation']['candidates'][0]['path'].endswith('sample.exe')


def test_wsl_is_not_native_windows(tmp_path):
    result=discover(profile(),tmp_path,platform='windows',mode='wsl')
    assert result['context']['mode']=='wsl'
    assert result['readiness']['host_verified'] is False


def test_multiple_candidates_are_ambiguous(tmp_path):
    p=profile();p['executables']=['sample'];a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    for folder in (a,b):(folder/'sample').write_bytes(b'not executed')
    assert discover(p,tmp_path,search_roots=[str(a),str(b)])['installation']['state']=='ambiguous'


def test_discovery_never_reads_transcripts_or_credentials(tmp_path):
    p=profile();secret=tmp_path/'private';secret.mkdir();(secret/'chat.jsonl').write_text('DO_NOT_READ')
    p['config']['paths']['macos']=['private/chat.jsonl']
    result=discover(p,tmp_path)
    assert 'DO_NOT_READ' not in str(result)
    assert result['configuration']['state']=='present'


def test_absent_is_not_failed(tmp_path):
    p=profile();p['executables']=['missing']
    result=discover(p,tmp_path,search_roots=[str(tmp_path)])
    assert result['installation']['state']=='not_installed'
    assert result['status']!='failed'


def test_configuration_metadata_change_invalidates_preparation_signature(tmp_path):
    p=profile();p['config']['paths']['macos']=['mcp.json']
    config=tmp_path/'mcp.json';config.write_text('{}')
    first=discover(p,tmp_path)['context']['config_sha256']
    config.write_text('{"operator_change":true}')
    second=discover(p,tmp_path)['context']['config_sha256']
    assert first!=second


def test_windows_gui_install_metadata_is_a_candidate_not_capability_proof(tmp_path):
    p=profile();p['windows_display_names']=['WorkBuddy']
    result=discover(p,tmp_path,platform='windows',windows_apps=[{'display_name':'WorkBuddy',
        'version':'5.test','location':'C:/Apps/WorkBuddy','registry_key':'synthetic-uninstall-entry'}])
    assert result['installation']['state']=='detected'
    assert result['installation']['candidates'][0]['version']=='5.test'
    assert result['readiness']['host_verified'] is False


def test_windows_lookalike_gui_name_is_not_matched(tmp_path):
    p=profile();p['windows_display_names']=['WorkBuddy']
    result=discover(p,tmp_path,platform='windows',windows_apps=[{'display_name':'WorkBuddy Helper','version':'x'}])
    assert result['installation']['state']!='detected'


def test_windows_registry_scan_is_bounded_and_reads_only_metadata(monkeypatch):
    import sys
    from types import SimpleNamespace
    from lib.host_integration.environment import _windows_app_metadata
    reads=[]
    class Key:
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def query(key,name):
        reads.append(name)
        return {'DisplayName':'WorkBuddy','DisplayVersion':'test','InstallLocation':'C:/Test'}[name],1
    fake=SimpleNamespace(HKEY_CURRENT_USER=1,HKEY_LOCAL_MACHINE=2,KEY_READ=4,
        KEY_WOW64_64KEY=8,KEY_WOW64_32KEY=16,REG_SZ=1,REG_EXPAND_SZ=2,
        OpenKey=lambda *args:Key(),EnumKey=lambda parent,index:str(index),QueryValueEx=query)
    monkeypatch.setitem(sys.modules,'winreg',fake)
    rows,status=_windows_app_metadata()
    assert len(rows)==512 and status=='limited'
    assert set(reads)=={'DisplayName','DisplayVersion','InstallLocation'}


def test_windows_discovery_never_exports_unrelated_application_inventory(tmp_path):
    from lib.host_integration.environment import discover_hosts
    p=profile();p['windows_display_names']=['WorkBuddy']
    result=discover_hosts({'profiles':[p]},{'platform':'windows','home':str(tmp_path),
        'search_roots':[],'windows_apps':[{'display_name':'Unrelated Private App','version':'secret'}]})
    assert 'Unrelated Private App' not in str(result)
    assert 'windows_apps' not in result['environment']


def test_windows_registry_permission_gap_does_not_claim_complete_scan(monkeypatch):
    import sys
    from types import SimpleNamespace
    from lib.host_integration.environment import _windows_app_metadata
    class Key:
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def open_key(hive,*args):
        if hive==2:raise PermissionError('synthetic access denied')
        return Key()
    def enumerate_key(*args):
        error=OSError('synthetic no more items');error.winerror=259;raise error
    monkeypatch.setitem(sys.modules,'winreg',SimpleNamespace(HKEY_CURRENT_USER=1,
        HKEY_LOCAL_MACHINE=2,KEY_READ=4,KEY_WOW64_64KEY=8,KEY_WOW64_32KEY=16,
        OpenKey=open_key,EnumKey=enumerate_key))
    assert _windows_app_metadata()==([], 'limited')
