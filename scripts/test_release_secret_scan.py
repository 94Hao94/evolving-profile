"""Release-source scan boundaries; fixtures never contain real credentials."""
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def setup(tmp_path):
    root=tmp_path/'package';(root/'scripts').mkdir(parents=True)
    for name in ('check-no-secrets.sh','scan-release-secrets.py'):
        if (ROOT/'scripts'/name).exists():shutil.copy2(ROOT/'scripts'/name,root/'scripts'/name)
    (root/'README.md').write_text('# Test source\n')
    (root/'.env.example').write_text('EP_BANK_ID=personal-memory\n')
    return root


def scan(root):
    return subprocess.run(['bash',str(root/'scripts/check-no-secrets.sh')],cwd=root,text=True,capture_output=True,timeout=15)


def test_installed_dependency_example_does_not_break_repeat_install(tmp_path):
    root=setup(tmp_path);p=root/'api/.venv/lib/vendor';p.mkdir(parents=True)
    (p/'example.txt').write_text('example '+ 'AKIA'+'A'*16)
    result=scan(root)
    assert result.returncode==0,result.stdout+result.stderr


def test_untracked_local_env_is_not_release_source_but_template_is_scanned(tmp_path):
    root=setup(tmp_path);key='sk-'+'a'*32
    (root/'.env').write_text('LOCAL_KEY='+key)
    assert scan(root).returncode==0
    (root/'.env.example').write_text('EXAMPLE_KEY='+key)
    result=scan(root)
    assert result.returncode!=0 and key not in result.stdout+result.stderr


def test_real_source_secret_is_rejected_without_echoing_its_value(tmp_path):
    root=setup(tmp_path);key='sk-'+'b'*32
    (root/'config.py').write_text('key='+key)
    result=scan(root)
    assert result.returncode!=0
    assert 'config.py' in result.stdout+result.stderr
    assert key not in result.stdout+result.stderr


def test_tracked_local_environment_cannot_be_hidden_by_local_env_exclusion(tmp_path):
    root=setup(tmp_path)
    subprocess.run(['git','init','-q'],cwd=root,check=True)
    (root/'.env').write_text('EP_BANK_ID=test-only\n')
    subprocess.run(['git','add','.env'],cwd=root,check=True)
    result=scan(root)
    assert result.returncode!=0 and 'tracked_local_environment' in result.stdout+result.stderr


def test_directory_source_symlinks_are_rejected_without_following_private_target(tmp_path):
    root=setup(tmp_path);outside=tmp_path/'outside';outside.mkdir()
    (outside/'config.py').write_text('synthetic='+ 'sk-'+'z'*32)
    (root/'source-linked-dir').symlink_to(outside,target_is_directory=True)
    for tracked in (False,True):
        if tracked:
            subprocess.run(['git','init','-q'],cwd=root,check=True)
            subprocess.run(['git','add','source-linked-dir'],cwd=root,check=True)
        result=scan(root)
        assert result.returncode!=0 and 'unverified_source_symlink' in result.stdout


def test_tracked_prefixed_vendor_directory_cannot_bypass_release_payload_guard(tmp_path):
    root=setup(tmp_path);subprocess.run(['git','init','-q'],cwd=root,check=True)
    p=root/'node_modules.custom';p.mkdir();(p/'source.py').write_text('synthetic='+ 'sk-'+'y'*32)
    subprocess.run(['git','add','node_modules.custom/source.py'],cwd=root,check=True)
    result=scan(root)
    assert result.returncode!=0 and 'tracked_runtime_artifact' in result.stdout


def test_author_home_path_cannot_ship_in_release_source(tmp_path):
    root=setup(tmp_path);private_home=str(Path.home())
    (root/'config.py').write_text('author_path='+repr(private_home+'/Documents/private-project'))
    result=scan(root)
    assert result.returncode!=0 and 'local_home_path' in result.stdout
    assert private_home not in result.stdout+result.stderr


def test_worktree_metadata_pointer_is_not_release_text_source(tmp_path):
    root=setup(tmp_path)
    (root/'.git').write_text('gitdir: '+str(Path.home()/'private-fixture-gitdir'))
    assert scan(root).returncode==0


def test_untracked_task_workspace_is_excluded_but_tracked_task_files_are_rejected(tmp_path):
    root=setup(tmp_path);folder=root/'.superpowers';folder.mkdir()
    (folder/'private-ledger.md').write_text(str(Path.home()/'private-audit'))
    assert scan(root).returncode==0
    subprocess.run(['git','init','-q'],cwd=root,check=True)
    subprocess.run(['git','add','-f','.superpowers/private-ledger.md'],cwd=root,check=True)
    result=scan(root)
    assert result.returncode!=0 and 'tracked_runtime_artifact' in result.stdout
