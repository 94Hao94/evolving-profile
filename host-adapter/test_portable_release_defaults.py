"""Published entrypoints must load the bundled package, not the author's checkout."""
import json,os,subprocess,sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('entry',['evolving_profile_controller_mcp.py','hindsight_controller_mcp.py','guidance_entry.py'])
def test_guidance_defaults_are_package_relative_and_home_scoped(entry,tmp_path):
    script='''
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]);temporary=Path(sys.argv[3])
Path.home=classmethod(lambda cls:temporary)
sys.path[:0]=[str(root/'host-adapter'),str(root/'guidance')]
spec=importlib.util.spec_from_file_location('portable_entry',root/'host-adapter'/sys.argv[2]);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
src=getattr(module,'GUIDANCE_V1_SRC',getattr(module,'GUIDANCE_SRC',None))
cfg=getattr(module,'GUIDANCE_V1_CONFIG',getattr(module,'GUIDANCE_CONFIG',None))
print(json.dumps({'source':str(Path(src).resolve()),'config':str(Path(cfg).resolve())}))
'''
    env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','USER','LOGNAME','LANG','TMPDIR'}}
    result=subprocess.run([sys.executable,'-c',script,str(ROOT),entry,str(tmp_path)],env=env,cwd=tmp_path,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    actual=json.loads(result.stdout.splitlines()[-1])
    assert Path(actual['source'])==ROOT/'guidance'
    assert Path(actual['config']).is_relative_to(tmp_path)


def test_retrieval_quality_bridge_loads_the_bundled_implementation():
    script='''
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'host-adapter'))
from lib.retrieval_quality import build_retrieval_contract
print(json.dumps({'implementation':build_retrieval_contract.__code__.co_filename}))
'''
    result=subprocess.run([sys.executable,'-c',script,str(ROOT)],text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert Path(json.loads(result.stdout)['implementation'])==ROOT/'guidance/retrieval_quality.py'


def test_hook_entry_honors_the_same_explicit_guidance_overrides(tmp_path):
    source=tmp_path/'custom-guidance';source.mkdir();config=tmp_path/'custom-registry.json'
    script='''
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'host-adapter'),str(root/'guidance')]
spec=importlib.util.spec_from_file_location('portable_override',root/'host-adapter/guidance_entry.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
print(json.dumps({'source':str(m.GUIDANCE_SRC),'config':str(m.GUIDANCE_CONFIG)}))
'''
    env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','USER','LOGNAME','LANG','TMPDIR'}}
    env.update(EVOLVING_PROFILE_GUIDANCE_SRC=str(source),EVOLVING_PROFILE_GUIDANCE_CONFIG=str(config))
    result=subprocess.run([sys.executable,'-c',script,str(ROOT)],env=env,cwd=tmp_path,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout.splitlines()[-1])=={'source':str(source),'config':str(config)}


@pytest.mark.parametrize('mode', ['unset', 'script_only', 'baseline_only', 'empty_script', 'empty_baseline', 'both'])
def test_legacy_rollback_requires_two_explicit_nonempty_paths(tmp_path, mode):
    """Inspect the opt-in gate without running any external rollback program."""
    rollback_script=tmp_path/'rollback.sh';rollback_script.touch()
    baseline=tmp_path/'baseline';baseline.mkdir()
    env={k:v for k,v in os.environ.items() if not k.startswith('EP_LEGACY_ROLLBACK_')}
    if mode in {'script_only','empty_baseline','both'}:
        env['EP_LEGACY_ROLLBACK_SCRIPT']=str(rollback_script)
    if mode in {'baseline_only','empty_script','both'}:
        env['EP_LEGACY_ROLLBACK_BASELINE']=str(baseline)
    if mode=='empty_script':env['EP_LEGACY_ROLLBACK_SCRIPT']=''
    if mode=='empty_baseline':env['EP_LEGACY_ROLLBACK_BASELINE']=''
    probe='''
import json,runpy,sys
namespace=runpy.run_path(sys.argv[1],run_name='rollback_gate_probe')
print(json.dumps({'skipped':bool(getattr(namespace['RollbackDrillTest'],'__unittest_skip__',False))}))
'''
    result=subprocess.run([sys.executable,'-c',probe,str(ROOT/'host-adapter/test_rollback_drill.py')],env=env,cwd=tmp_path,text=True,capture_output=True,timeout=20)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['skipped'] is (mode!='both')
