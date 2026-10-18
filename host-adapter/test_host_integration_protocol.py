import json
import os
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]


def probe_env(tmp_path):
    return {**os.environ,'EVOLVING_PROFILE_STATE_ROOT':str(tmp_path),
        'EVOLVING_PROFILE_GUIDANCE_CONFIG':str(tmp_path/'missing.json'),
        'EVOLVING_PROFILE_HOST_ID':'workbuddy','EVOLVING_PROFILE_ACCESS_MODE':'read-only',
        'PYTHONPATH':os.pathsep.join(str(ROOT/p) for p in ('guidance','host-adapter','controller','ham-os'))}


def test_handshake_and_catalog_is_probe_not_host_proof(tmp_path):
    from lib.host_integration.protocol import probe_stdio
    runner='import runpy,sys;from pathlib import Path;Path.home=classmethod(lambda cls:Path(sys.argv[1]));runpy.run_path(sys.argv[2],run_name="__main__")'
    result=probe_stdio([sys.executable,'-c',runner,str(tmp_path),str(ROOT/'host-adapter/evolving_profile_controller_mcp.py')],probe_env(tmp_path))
    assert result['status']=='protocol_verified'
    assert result['evidence_kind']=='isolated_probe'
    assert result['host_verified'] is False
    assert 'user_recall' in result['tool_names']
    assert 'promote_agent_process_memory' not in result['tool_names']
    assert result['knowledge_calls']==0 and result['provider_calls']==0


def test_stdout_noise_and_oversize_fail_bounded(tmp_path):
    from lib.host_integration.protocol import probe_stdio
    for output in ('noise','x'*1000):
        result=probe_stdio([sys.executable,'-c','print('+repr(output)+')'],probe_env(tmp_path))
        assert result['status']=='failed' and result['host_verified'] is False


def test_probe_timeout_is_bounded(tmp_path):
    from lib.host_integration.protocol import probe_stdio
    result=probe_stdio([sys.executable,'-c','import time;time.sleep(30)'],probe_env(tmp_path),timeout_seconds=0.1)
    assert result['error_stage']=='handshake'
    assert result['error_code']=='timeout'


def test_stdio_direct_disabled_tool_is_rejected_before_execution(tmp_path):
    import subprocess
    env=probe_env(tmp_path)
    runner='import runpy,sys;from pathlib import Path;Path.home=classmethod(lambda cls:Path(sys.argv[1]));runpy.run_path(sys.argv[2],run_name="__main__")'
    request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'record_agent_trajectory','arguments':{}}}
    run=subprocess.run([sys.executable,'-c',runner,str(tmp_path),str(ROOT/'host-adapter/evolving_profile_controller_mcp.py')],
        input=json.dumps(request)+'\n',env=env,text=True,capture_output=True,timeout=10,check=True)
    reply=json.loads(run.stdout)
    assert reply['error']['code']==-32001
    assert not list(tmp_path.rglob('process-memory.json'))
