"""Real stdio server rejects bad arguments and survives for a corrected retry."""
import json
import os
import subprocess
import sys
from pathlib import Path


def test_invalid_guidance_arguments_have_structured_errors_and_retry_succeeds(tmp_path):
    root = Path(__file__).resolve().parents[1]
    runner = '''import runpy,sys,json
from pathlib import Path
Path.home=classmethod(lambda cls:Path(sys.argv[1]))
binding_calls=[]
def profile(frame,event,arg):
    if event=='call' and frame.f_code.co_name=='_prompt_binding_for_check_id':
        binding_calls.append(frame.f_globals.get('request',{}).get('id'))
sys.setprofile(profile)
runpy.run_path(sys.argv[2],run_name='__main__')
sys.setprofile(None)
Path(sys.argv[3]).write_text(json.dumps(binding_calls))
'''
    config = tmp_path / 'guidance.json'
    config.write_text(json.dumps({'registry': str(tmp_path / 'registry.sqlite'), 'bank_id': 'test'}))
    valid = {'task': {'objective': 'Recover a failed tool', 'phase': 'verify'},
             'runtime_event': {'failure': 'dependency_install_failure'}}
    arguments = [
        ('refresh_runtime_guidance', {'task': 'Render video', 'runtime_events': [
            {'event': 'npm_failure', 'details': 'not a canonical runtime event'}]}),
        ('refresh_runtime_guidance', {'task': {'objective': 'render'},
                                    'runtime_events': [{'event': 'npm_failure'}]}),
        ('user_preference', {'check_id': 'test-only-check', 'task': 'wrong shape'}),
        ('user_preference', {'task': 'wrong shape'}),
        ('user_preference', {'task': {'objective': 'a task'}}),
    ]
    for tool in ('refresh_runtime_guidance', 'user_preference'):
        for invalid in ('bad arguments', ['not', 'an', 'object'], None, False, 0, []):
            arguments.append((tool, invalid))
    arguments.append(('refresh_runtime_guidance', valid))
    requests = [{'jsonrpc': '2.0', 'id': i + 1, 'method': 'tools/call',
                 'params': {'name': name, 'arguments': args}}
                for i, (name, args) in enumerate(arguments)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=os.pathsep.join(str(root / p) for p in ('host-adapter', 'guidance', 'controller', 'ham-os')),
               EVOLVING_PROFILE_STATE_ROOT=str(tmp_path / '.evolving-profile'),
               EVOLVING_PROFILE_GUIDANCE_SRC=str(root / 'guidance'),
               EVOLVING_PROFILE_GUIDANCE_CONFIG=str(config))
    run = subprocess.run([sys.executable, '-c', runner, str(tmp_path),
                          str(root / 'host-adapter/evolving_profile_controller_mcp.py'),
                          str(tmp_path / 'binding-calls.json')],
                         input=''.join(json.dumps(r) + '\n' for r in requests),
                         text=True, capture_output=True, timeout=20, env=env, check=True)
    rows = {r['id']: r for r in map(json.loads, run.stdout.splitlines())}
    expected_errors = [(1, 'task'), (2, 'runtime_event'), (3, 'task'), (4, 'task'), (5, 'check_id')]
    expected_errors += [(identity, 'arguments') for identity in range(6, len(requests))]
    for identity, field in expected_errors:
        error = rows[identity]['error']
        assert error['code'] == -32602, error
        assert field in error['message']
        assert error['data']['field'] == field
        assert 'recovery' not in error['data']
        assert 'AttributeError' not in error['message'] and "has no attribute" not in error['message']
    result = json.loads(rows[len(requests)]['result']['content'][0]['text'])
    assert result['mode'] == 'runtime_guidance_refresh'
    assert result['long_term_model_created'] is False
    assert result['persistence'] == 'none_current_turn_only'
    binding_calls = json.loads((tmp_path / 'binding-calls.json').read_text())
    assert len(requests) in binding_calls
    assert not set(range(1, len(requests))) & set(binding_calls)
