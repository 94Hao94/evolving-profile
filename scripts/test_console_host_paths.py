"""Exercise the real Console launcher: cwd changes must not lose EP host scripts."""
import json,os,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def launch(tmp_path,override=None):
    root=tmp_path/'EP 中文 path';(root/'console/bin').mkdir(parents=True)
    (root/'console/standalone').mkdir();(root/'scripts').mkdir()
    shutil.copy2(ROOT/'console/bin/cli.js',root/'console/bin/cli.js')
    (root/'scripts/ep-host.py').write_text('# synthetic preparation entry\n')
    (root/'console/standalone/server.js').write_text(
        'console.log(JSON.stringify({source:process.env.EVOLVING_PROFILE_HOST_SOURCE_ROOT??null,cwd:process.cwd()}));')
    env={k:v for k,v in os.environ.items() if k!='EVOLVING_PROFILE_HOST_SOURCE_ROOT'}
    if override is not None:env['EVOLVING_PROFILE_HOST_SOURCE_ROOT']=override
    result=subprocess.run([shutil.which('node'),str(root/'console/bin/cli.js'),'--hostname','127.0.0.1'],
        cwd=tmp_path,env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    return root,json.loads(result.stdout.splitlines()[-1])

def test_launcher_keeps_host_root_after_entering_standalone(tmp_path):
    root,result=launch(tmp_path)
    assert result['source']==str(root)
    assert result['cwd']==str(root/'console/standalone')

def test_launcher_preserves_explicit_separate_host_bundle(tmp_path):
    _,result=launch(tmp_path,'/operator/selected EP')
    assert result['source']=='/operator/selected EP'
