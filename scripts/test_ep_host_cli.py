import json
import subprocess
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable,str(ROOT/'scripts/ep-host.py'),*args],text=True,encoding='utf-8',capture_output=True,timeout=20)


def test_list_is_registry_projection_without_host_certification():
    p=run('list','--json');assert p.returncode==0,p.stderr
    data=json.loads(p.stdout)
    assert len(data['profiles'])==8 and data['schema']=='ep.host-registry.v1'
    assert 'host_verified' not in p.stdout


def test_doctor_missing_unknown_is_not_fault_and_no_probe(tmp_path):
    p=run('doctor','--host','generic_mcp','--state-root',str(tmp_path),'--json')
    assert p.returncode==0,p.stderr
    data=json.loads(p.stdout)
    assert data['hosts'][0]['installation']['state']=='unknown'
    assert data['provider_calls']==0 and data['host_tasks_started']==0
    assert not list(tmp_path.rglob('*.json'))


def test_config_preview_and_denied_apply_do_not_write_target(tmp_path):
    target=tmp_path/'mcp.json'
    p=run('config-preview','--host','workbuddy','--target',str(target),'--state-root',str(tmp_path),'--json')
    assert p.returncode==0,p.stderr
    plan=json.loads(p.stdout)
    assert plan['apply_supported'] is True and not target.exists()
    p=run('config-apply','--host','workbuddy','--state-root',str(tmp_path),'--json')
    assert p.returncode!=0 and not target.exists()


def test_guide_chinese_and_unknown_host_are_explicit():
    p=run('guide','--host','doubao_work','--locale','zh-CN','--json')
    assert p.returncode==0 and json.loads(p.stdout)['mandatory_each_turn'] is False
    p=run('doctor','--host','unknown-host','--json')
    assert p.returncode!=0 and json.loads(p.stdout)['error_code']=='unknown_host_profile'


def test_matrix_needs_no_host_and_is_registry_generated():
    p=run('matrix','--locale','en','--format','markdown')
    assert p.returncode==0,p.stdout
    assert '| workbuddy |' in p.stdout and '| doubao_work |' in p.stdout


def test_probe_receipt_updates_only_protocol_state_and_survives_refresh(tmp_path):
    p=run('doctor','--host','generic_mcp','--probe','--state-root',str(tmp_path),'--json')
    assert p.returncode==0,p.stdout
    result=json.loads(p.stdout)
    assert result['protocol_probe']['status']=='protocol_verified'
    p=run('discover','--host','generic_mcp','--state-root',str(tmp_path),'--json')
    result=json.loads(p.stdout)['hosts'][0]['readiness']
    assert result['capabilities']['mcp_stdio']['state']=='protocol_verified'
    assert result['host_verified'] is False and result['capture_enabled'] is False


def test_cli_json_utf8_is_independent_of_terminal_codepage():
    p=subprocess.run([sys.executable,str(ROOT/'scripts/ep-host.py'),'list','--json'],
        env={**os.environ,'PYTHONIOENCODING':'ascii'},text=True,encoding='utf-8',capture_output=True,timeout=20)
    assert p.returncode==0,p.stderr
    assert next(r for r in json.loads(p.stdout)['profiles'] if r['id']=='doubao_work')['labels']['zh-CN']=='豆包工作任务'
