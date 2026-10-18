import json
import recall
import io
import pytest


def test_ingress_records_exact_native_context_without_credentials(tmp_path):
    path = tmp_path/'ingress.jsonl'
    recall.record_prompt_ingress({'promptIngressAuditPath':str(path)}, 'Review project', 's', '/project',
        turn_id='t',hook_invocation_id='c',transcript_path='/raw/s.jsonl',model='actual-model',model_provider='configured-provider')
    row = json.loads(path.read_text())
    assert row['cwd'] == '/project'
    assert row['transcript_path'] == '/raw/s.jsonl'
    assert row['model'] == 'actual-model'
    assert row['model_provider'] == 'configured-provider'


def test_native_task_identity_is_available_before_hook_guidance_selection(tmp_path, monkeypatch):
    ingress = tmp_path / '.evolving-profile/audit/prompt-ingress.jsonl'
    monkeypatch.setattr(recall, 'load_config', lambda: {'autoRecall': True,
        'promptIngressAuditPath': str(ingress), 'agentOwnedGuidance': True})
    monkeypatch.setattr(recall, 'ham_emit', lambda *args, **kw: {'capture_durable': True})
    monkeypatch.setattr(recall, 'is_shadow_replay', lambda: False)
    observed = {}
    class SelectionReached(BaseException): pass
    def selection(hook, prompt, **kw):
        observed['rows'] = [json.loads(line) for line in ingress.read_text().splitlines()] if ingress.exists() else []
        observed['check_id'] = hook['hook_invocation_id']
        raise SelectionReached()
    monkeypatch.setattr(recall, 'prepare_agent_owned_entry', selection)
    monkeypatch.setattr('sys.stdin', io.StringIO(json.dumps({'prompt': '继续修改讲座，保留论点。',
        'session_id': 'native-session', 'turn_id': 'native-turn', 'task_id': 'native-task', 'cwd': '/task'})))
    with pytest.raises(SelectionReached): recall.main()
    assert len(observed['rows']) == 1
    assert observed['rows'][0]['task_id'] == 'native-task'
    assert observed['rows'][0]['hook_invocation_id'] == observed['check_id']
