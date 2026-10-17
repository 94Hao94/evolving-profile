"""Fresh public adapters and real selector/repository, isolated from live data."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = r'''
import io,json,sys
from pathlib import Path
root=Path(sys.argv[1]);adapter=sys.argv[2]
Path.home=classmethod(lambda cls:root)
sys.stdin=io.StringIO('')
import evolving_profile_controller_mcp as mcp
from repository import GuidanceRepository
repo=GuidanceRepository(root/'registry.sqlite','bank')
for identity,scope in [('session-local',{'session_ids':['native-session']}),
                       ('task-local',{'task_ids':['native-task']}),
                       ('other-local',{'session_ids':['session-without-task']})]:
    unit={'id':identity,'revision':'r1','text':'讲座修改必须保留核心论点。','applies_when':['讲座修改'],
        'exceptions':['当前要求优先'],'scope':scope,'primary_category':'communication','evidence_refs':[]}
    repo.store_active_unit_for_migration(unit)
    repo.set_unit_audit(identity,'r1',{'state':'restricted','reason':'synthetic fixture scope'})
config=root/'config.json';config.write_text(json.dumps({'registry':str(repo.path),'bank_id':'bank'}))
mcp.GUIDANCE_V1_CONFIG=str(config)
ingress=root/'.evolving-profile/audit/prompt-ingress.jsonl';ingress.parent.mkdir(parents=True)
rows=[{'at':'2026-01-01T00:00:00Z','hook_invocation_id':'check-known-task',
       'session_id':'native-session','turn_id':'t1','task_id':'native-task'},
      {'at':'2026-01-01T00:01:00Z','hook_invocation_id':'check-without-task',
       'session_id':'session-without-task','turn_id':'t2'}]
ingress.write_text(''.join(json.dumps(row)+'\n' for row in rows))
def call(check):
    request={'check_id':check,'task':{'objective':'讲座修改，保留核心论点。','phase':'execute',
        'session_id':'native-session','session_ids':['native-session'],
        'task_id':'native-task','task_ids':['native-task']},'memory_policy':'allowed','loaded':[],
        'runtime_event':{'failure':'工具失败'}}
    if adapter=='preference': result=json.loads(mcp.preference(request)['content'][0]['text'])
    elif adapter=='runtime': result=json.loads(mcp.runtime_guidance(request)['content'][0]['text'])
    elif adapter=='direct_preference':
        from mcp_runtime import get_preference_response
        result=get_preference_response(repo,request,record=False)
    elif adapter=='direct_runtime':
        from runtime_recovery import refresh_runtime_guidance
        result=refresh_runtime_guidance(repo,request)
    else:
        from guidance_entry import build_request
        from mcp_runtime import get_preference_response
        request=build_request({'session_id':'forged-hook-id'},'讲座修改，保留核心论点。','entry:'+check)
        request.pop('semantic_recall',None)
        result=get_preference_response(repo,request,record=False)
    return sorted(item['id'] for item in result['included'])
binding=mcp._prompt_binding_for_check_id('check-known-task','2026-10-15T00:00:00Z')
print(json.dumps({'known':call('check-known-task'),'without_task':call('check-without-task'),
    'unknown':call('check-missing'),'binding_task':binding.get('task_id')}))
'''


@pytest.mark.parametrize('adapter', ['preference', 'runtime', 'direct_preference', 'direct_runtime', 'hook_entry'])
def test_scoped_preferences_all_public_consumers_bind_native_identity(tmp_path, adapter):
    dev = Path(__file__).resolve().parents[1]
    env = dict(os.environ, EVOLVING_PROFILE_GUIDANCE_SRC=str(dev / 'guidance'),
        PYTHONPATH=os.pathsep.join(str(dev / name) for name in ('host-adapter','guidance','controller','ham-os')),
        EVOLVING_PROFILE_STATE_ROOT=str(tmp_path / '.evolving-profile'))
    run = subprocess.run([sys.executable, '-c', SCRIPT, str(tmp_path), adapter], env=env,
        text=True, capture_output=True, check=True, timeout=15)
    result = json.loads(run.stdout.splitlines()[-1])
    assert result['known'] == ['session-local', 'task-local']
    assert result['without_task'] == ['other-local']
    assert result['unknown'] == []
    assert result['binding_task'] == 'native-task'
