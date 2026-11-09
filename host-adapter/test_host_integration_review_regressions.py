import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'guidance'))


@pytest.fixture
def core(tmp_path,monkeypatch):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path))
    monkeypatch.setenv('EVOLVING_PROFILE_GUIDANCE_CONFIG',str(tmp_path/'missing.json'))
    monkeypatch.setenv('EVOLVING_PROFILE_GUIDANCE_SRC',str(ROOT/'guidance'))
    monkeypatch.setenv('HINDSIGHT_TURN_CHECK_ROOT',str(tmp_path/'turn-checks'))
    monkeypatch.setenv('EVOLVING_PROFILE_ROUTE_RECEIPT_ROOT',str(tmp_path/'receipts'))
    spec=importlib.util.spec_from_file_location('host_scope_review_core',ROOT/'host-adapter/evolving_profile_controller_mcp.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def scope(monkeypatch,host='workbuddy',owner='owner',instance='one'):
    monkeypatch.setenv('EVOLVING_PROFILE_HOST_ID',host)
    monkeypatch.setenv('EVOLVING_PROFILE_INSTALLATION_ID',instance)
    monkeypatch.setenv('EVOLVING_PROFILE_OWNER_ID',owner)


def binding(host='workbuddy',owner='owner',instance='one'):
    return {'state':'prompt_bound','host_id':host,'owner_id':owner,'installation_id':instance,
            'session_id':'same','turn_id':'turn','hook_invocation_id':'same-check'}


def test_receipt_namespace_survives_actual_route_consumer(core,tmp_path,monkeypatch):
    scope(monkeypatch)
    path,receipt=core._route_receipt_for_binding(tmp_path,'same-check',binding())
    receipt['tool_events']=[{'tool':'user_recall','owner':'workbuddy'}];path.write_text(json.dumps(receipt))
    scope(monkeypatch,'doubao_work',instance='two')
    other,receipt=core._route_receipt_for_binding(tmp_path,'same-check',binding('doubao_work',instance='two'))
    assert other!=path and not receipt.get('tool_events')


def test_binding_and_source_selection_preserve_owner_namespace(core,tmp_path,monkeypatch):
    from context_binding import resolve_prompt_binding
    scope(monkeypatch)
    folder=tmp_path/'.evolving-profile/audit';folder.mkdir(parents=True)
    rows=[{**binding(),'at':'2026-10-18T00:00:00Z','prompt_preview':'synthetic budget 10万元'},
          {**binding(owner='other'),'at':'2026-10-18T00:00:00Z','prompt_preview':'synthetic budget 99万元'}]
    (folder/'prompt-ingress.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    b=resolve_prompt_binding('same-check','2026-10-18T01:00:00Z',tmp_path)
    assert b['owner_id']=='owner' and b['installation_id']=='one'
    result=core._query_scope_audit('same-check','99万元',b,tmp_path)
    assert result['status']=='review_added_anchors' and result['added_amounts_wan']==['99']
    core.CURRENT_TOOL_CALL={'binding_at_start':b,'invocation_started_at':'2026-10-18T01:00:00Z'}
    declared=core.memory_check_declaration({'check_id':'same-check','need':'required','full_prompt':'synthetic task','reason':'test'})
    assert declared['original_prompt']=='synthetic budget 10万元'


def test_new_host_cannot_use_legacy_codex_check_registry(core,tmp_path,monkeypatch):
    from memory_turn_check import register
    register({'invocation_id':'legacy-check','session_id':'s','turn_id':'t','raw_prompt':'synthetic codex only'})
    scope(monkeypatch)
    with pytest.raises(ValueError):
        core.memory_check_declaration({'check_id':'legacy-check','need':'required','full_prompt':'q','reason':'test'})


def test_owned_config_keeps_permission_and_operator_environment(tmp_path):
    from lib.host_integration.configuration import OWNER,plan_configuration,apply_configuration
    p=tmp_path/'mcp.json'
    p.write_text(json.dumps({'mcpServers':{'evolving_profile_controller':{'command':'/old/python',
       'disabled':True,'autoApprove':[],'env':{'EVOLVING_PROFILE_INTEGRATION_OWNER':OWNER,
       'EVOLVING_PROFILE_HOST_ID':'workbuddy','OPERATOR_SETTING':'keep'}}}}))
    plan=plan_configuration({'id':'workbuddy','config':{'format':'json','apply':True}},p,{'command':'/new/python','args':[],'env':{}})
    apply_configuration(plan,expected_sha256=plan['before_sha256'])
    entry=json.loads(p.read_text())['mcpServers']['evolving_profile_controller']
    assert entry['disabled'] is True and entry['autoApprove']==[] and entry['env']['OPERATOR_SETTING']=='keep'
    assert 'command' in plan['changed_fields']


def test_windows_interpreter_alone_is_not_execution_evidence(monkeypatch):
    from lib.host_integration import acceptance
    monkeypatch.setattr(acceptance,'os',SimpleNamespace(name='nt'))
    out=acceptance.build_acceptance_manifest([{'status':'passed','evidence_kind':'fixture','provider_calls':0}],{'profiles':[]})
    assert out['windows_execution']=='not_run'


def test_returned_content_archive_keeps_host_namespace(tmp_path):
    from lib.returned_content import archive_returned_items
    item={'id':'synthetic','text':'same synthetic text','role':'candidate'}
    call={'tool_call_id':'same-call'}
    a=archive_returned_items(tmp_path,'user_recall',[item],binding(),call)
    b=archive_returned_items(tmp_path,'user_recall',[item],binding('doubao_work',instance='two'),call)
    assert a['ref']!=b['ref']
