"""Installer side effects and failure recovery; real installer/package preflight."""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def package(tmp_path):
    root=tmp_path/'package';root.mkdir()
    for folder in ('scripts','api','console','evolving-client','guidance','host-adapter'):(root/folder).mkdir()
    (root/'evolving-client/package.json').write_text('{"name":"@evolving-profile/client"}')
    for name in ('install-ep51.sh','release-preflight.py','verify-package.sh','check-no-secrets.sh','scan-release-secrets.py'):
        shutil.copy2(ROOT/'scripts'/name,root/'scripts'/name)
    (root/'VERSION').write_text('5.1.0\n')
    (root/'README.md').write_text('# Evolving Profile\n')
    (root/'NOTICE.md').write_text('# Attribution — Evolving Profile 5.1\n')
    (root/'CHANGELOG-5.1.md').write_text('# Evolving Profile 5.1.0\n')
    (root/'.env.example').write_text('EP_BANK_ID=personal-memory\n')
    for name in ('guidance_entry.py','evolving_profile_controller_mcp.py'):(root/'host-adapter'/name).write_text('pass\n')
    bin_dir=tmp_path/'bin';bin_dir.mkdir()
    npm=bin_dir/'npm'
    npm.write_text('''#!/usr/bin/env python3
import os,pathlib,sys
root=pathlib.Path(os.environ['INSTALL_FIXTURE_ROOT'])
if sys.argv[1:3]==['run','build']:
 if sys.argv[-1].endswith('/evolving-client'):
  (root/'evolving-client/dist').mkdir(exist_ok=True)
  (root/'evolving-client/dist/sdk-marker').write_text('new-sdk')
  if os.environ.get('INSTALL_FAIL_SDK')=='1':sys.exit(29)
  sys.exit(0)
 if os.environ.get('INSTALL_REQUIRE_SDK')=='1' and not (root/'evolving-client/dist/sdk-marker').exists():sys.exit(42)
 for name in ('.next','standalone'):
  (root/'console'/name).mkdir(exist_ok=True)
  (root/'console'/name/'build-marker').write_text('new-build')
 if os.environ.get('INSTALL_FAIL_BUILD')=='1':sys.exit(23)
''');npm.chmod(0o755)
    env={**os.environ,'PATH':str(bin_dir)+os.pathsep+os.environ['PATH'],
        'TMPDIR':str(tmp_path),'INSTALL_FIXTURE_ROOT':str(root)}
    return root,env


def install(root,env,*flags):
    return subprocess.run(['bash',str(root/'scripts/install-ep51.sh'),'--skip-deps','--no-launch',*flags],
        cwd=root,env=env,text=True,capture_output=True,timeout=30)


def snapshot(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_dry_run_does_not_create_temp_dirs_env_outputs_or_move_old_build(tmp_path):
    root,env=package(tmp_path)
    for name in ('.next','standalone'):
        (root/'console'/name).mkdir();(root/'console'/name/'build-marker').write_text('old-build')
    before=snapshot(tmp_path)
    result=install(root,env,'--dry-run')
    assert result.returncode==0,result.stderr
    assert snapshot(tmp_path)==before
    assert not list(tmp_path.glob('ep51-build.*'))


def test_failed_upgrade_restores_previous_build_and_preserves_existing_env(tmp_path):
    root,env=package(tmp_path)
    for name in ('.next','standalone'):
        (root/'console'/name).mkdir();(root/'console'/name/'build-marker').write_text('old-build')
    (root/'.env').write_text('EP_BANK_ID=existing-isolated-bank\n')
    result=install(root,{**env,'INSTALL_FAIL_BUILD':'1'})
    assert result.returncode==23
    assert (root/'console/.next/build-marker').read_text()=='old-build'
    assert (root/'console/standalone/build-marker').read_text()=='old-build'
    assert (root/'.env').read_text()=='EP_BANK_ID=existing-isolated-bank\n'
    assert 'restored' in result.stderr.lower()
    assert not (root/'output/ep51-local-launch.json').exists()


def test_successful_setup_preserves_existing_env_and_has_versioned_rollback_receipt(tmp_path):
    root,env=package(tmp_path)
    (root/'console/standalone').mkdir();(root/'console/standalone/build-marker').write_text('old-build')
    (root/'.env').write_text('EP_BANK_ID=existing-isolated-bank\n')
    result=install(root,env)
    assert result.returncode==0,result.stderr
    receipt=json.loads((root/'output/ep51-local-launch.json').read_text())
    assert receipt['version']=='5.1.0' and receipt['launch']=='manual'
    assert receipt['services_started'] is False
    assert Path(receipt['previous_build_backup']).joinpath('standalone/build-marker').read_text()=='old-build'
    assert (root/'console/standalone/build-marker').read_text()=='new-build'
    assert (root/'.env').read_text()=='EP_BANK_ID=existing-isolated-bank\n'


def test_invalid_mode_fails_before_changing_package(tmp_path):
    root,env=package(tmp_path);before=snapshot(root)
    result=install(root,env,'--mode','remote')
    assert result.returncode==2 and snapshot(root)==before


def test_backup_move_failure_does_not_move_unbacked_old_tree_out_of_place(tmp_path):
    root,env=package(tmp_path)
    for name in ('.next','standalone'):
        (root/'console'/name).mkdir();(root/'console'/name/'build-marker').write_text('old-build')
    move=tmp_path/'bin/mv'
    move.write_text('''#!/usr/bin/env python3
import os,pathlib,subprocess,sys
marker=pathlib.Path(os.environ['INSTALL_FIXTURE_ROOT'])/'move-failed-once'
if sys.argv[1].endswith('/console/.next') and not marker.exists():
 marker.write_text('injected backup move failure');sys.exit(27)
sys.exit(subprocess.call(['/bin/mv',*sys.argv[1:]]))
''');move.chmod(0o755)
    result=install(root,env)
    assert result.returncode==27
    assert (root/'console/.next/build-marker').read_text()=='old-build'
    assert (root/'console/standalone/build-marker').read_text()=='old-build'


def test_fresh_setup_builds_workspace_sdk_before_console_even_when_skipping_dependency_install(tmp_path):
    root,env=package(tmp_path)
    result=install(root,{**env,'INSTALL_REQUIRE_SDK':'1'})
    assert result.returncode==0,result.stderr
    assert (root/'console/standalone/build-marker').read_text()=='new-build'


def test_failed_sdk_upgrade_preserves_previous_sdk_and_console(tmp_path):
    root,env=package(tmp_path)
    (root/'evolving-client/dist').mkdir();(root/'evolving-client/dist/sdk-marker').write_text('old-sdk')
    (root/'console/standalone').mkdir();(root/'console/standalone/build-marker').write_text('old-build')
    result=install(root,{**env,'INSTALL_FAIL_SDK':'1'})
    assert result.returncode==29
    assert (root/'evolving-client/dist/sdk-marker').read_text()=='old-sdk'
    assert (root/'console/standalone/build-marker').read_text()=='old-build'


def test_partial_backup_move_never_overwrites_intact_original_with_partial_backup(tmp_path):
    root,env=package(tmp_path)
    for name in ('.next','standalone'):
        (root/'console'/name).mkdir()
        (root/'console'/name/'build-marker').write_text('old-build')
        (root/'console'/name/'extra-marker').write_text('complete-old-build')
    move=tmp_path/'bin/mv'
    move.write_text('''#!/usr/bin/env python3
import os,pathlib,shutil,subprocess,sys
marker=pathlib.Path(os.environ['INSTALL_FIXTURE_ROOT'])/'partial-move-once'
if sys.argv[1].endswith('/console/.next') and not marker.exists():
 marker.write_text('injected partial backup move');dst=pathlib.Path(sys.argv[2]);dst.mkdir()
 shutil.copy2(pathlib.Path(sys.argv[1])/'build-marker',dst/'build-marker');sys.exit(27)
sys.exit(subprocess.call(['/bin/mv',*sys.argv[1:]]))
''');move.chmod(0o755)
    result=install(root,env)
    assert result.returncode==27
    for name in ('.next','standalone'):
        assert (root/'console'/name/'extra-marker').read_text()=='complete-old-build'
    assert 'rollback incomplete' in result.stderr.lower()
    assert 'previous build restored' not in result.stderr.lower()
