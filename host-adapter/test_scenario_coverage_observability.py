"""Coverage bodies must survive the MCP -> receipt -> detail archive boundary."""
import contextlib
import io
import json

import pytest


def invoke(tmp_path, monkeypatch, body):
    import evolving_profile_controller_mcp as mcp
    binding = {'state': 'prompt_bound', 'hook_invocation_id': 'check-coverage',
               'session_id': 'host-session', 'turn_id': 'host-turn'}
    monkeypatch.setattr(mcp.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(mcp, 'capture_tool_trajectory', lambda *a, **kw: None)
    monkeypatch.setenv('EVOLVING_PROFILE_ROUTE_RECEIPT_ROOT', str(tmp_path / 'routes'))
    monkeypatch.setattr(mcp, 'CURRENT_TOOL_CALL', {'name': 'read_scenario_summary',
        'arguments': {'check_id': 'check-coverage', 'purpose': 'navigation'},
        'tool_call_id': 'coverage-call', 'binding_at_start': binding})
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        mcp.reply(1, result={'content': [{'type': 'text', 'text': json.dumps(body)}]})
    reply = json.loads(json.loads(output.getvalue())['result']['content'][0]['text'])
    activity = json.loads((tmp_path / '.evolving-profile/audit/mcp-tool-activity.jsonl').read_text().splitlines()[-1])
    route = json.loads(next((tmp_path / 'routes').glob('*.json')).read_text())
    return reply, activity, route


def envelope(view):
    return {'source': 'scenario_coverage_ledger', 'view': view,
            'scenario_id': 'session:source-session', 'snapshot_id': 'snapshot',
            'status': 'global_pending', 'semantic_review_status': 'not_reviewed',
            'source_readback': False, 'raw_source_status': 'not_read',
            'requirement_count': 41, 'has_unread_requirements': True,
            'external_fact_verified': False}


def test_requirement_page_count_and_exact_detail_are_not_zero_or_whole_inventory(tmp_path, monkeypatch):
    body = {**envelope('requirements'), 'requirements': [
        {'requirement_id': 'req-1', 'text': '不要删除原文件。', 'status': 'unresolved',
         'source_locator': {'raw_line_sha256': 'line-1'}}]}
    reply, activity, route = invoke(tmp_path, monkeypatch, body)
    assert reply['returned_count'] == 1
    assert activity['returned_count'] == route['tool_events'][0]['returned_count'] == 1
    assert activity['mapping_items'][0]['id'] == 'req-1'
    assert activity['mapping_items'][0]['text'] == '不要删除原文件。'
    assert activity['mapping_items'][0]['source_role'] == 'scenario_requirement'
    assert activity['scenario_coverage_view'] == 'requirements'
    assert activity['scenario_summary_status'] == 'global_pending'
    assert activity['original_message_readback_count'] == activity['source_read_count'] == 0
    snapshot = activity['returned_content_snapshot']
    stored = json.loads((tmp_path / '.evolving-profile/audit/returned-content' / (snapshot['ref'] + '.json')).read_text())
    assert stored['items'][0]['text'] == '不要删除原文件。'
    assert stored['items'][0]['source_locator']['raw_line_sha256'] == 'line-1'
    assert stored['item_count'] == 1


def test_source_readback_has_original_body_but_is_not_a_bank_read_source(tmp_path, monkeypatch):
    body = {**envelope('source'), 'source_readback': True, 'raw_source_status': 'source_read',
        'raw_source': {'text': '原始消息，不是模型摘要。', 'locators': [{'raw_line_sha256': 'line-1'}]},
        'raw_source_coverage': {'returned_messages': 1, 'partial': False}}
    reply, activity, route = invoke(tmp_path, monkeypatch, body)
    assert reply['returned_count'] == 1
    assert reply['original_message_readback_count'] == 1
    assert activity['original_message_readback_count'] == route['tool_events'][0]['original_message_readback_count'] == 1
    assert activity['source_read_count'] == 0
    assert activity['mapping_items'][0]['text'] == '原始消息，不是模型摘要。'
    assert activity['mapping_items'][0]['source_role'] == 'original_source'
    assert activity['mapping_items'][0]['source_locator']['locators'][0]['raw_line_sha256'] == 'line-1'
    assert reply.get('host_delivery') != 'observed'


def test_relation_page_keeps_exact_edges_without_claiming_source_readback(tmp_path, monkeypatch):
    body = {**envelope('relations'), 'relations': [
        {'type': 'supersedes', 'from': 'req-1', 'to': 'req-2', 'evidence_quote': '旧值改为新值'}]}
    reply, activity, _ = invoke(tmp_path, monkeypatch, body)
    assert reply['returned_count'] == 1
    row = activity['mapping_items'][0]
    assert row['source_role'] == 'scenario_relation'
    assert json.loads(row['text']) == body['relations'][0]
    assert activity['original_message_readback_count'] == 0


@pytest.mark.parametrize('body', [
    envelope('overview'),
    {**envelope('requirements'), 'requirements': []},
    {**envelope('source'), 'raw_source_status': 'source_unavailable', 'raw_source': {'text': 'not a successful read'}},
    {**envelope('source'), 'source_readback': True, 'raw_source_status': 'source_read', 'raw_source': {'text': ''}},
    {**envelope('requirements'), 'permission_status': 'denied', 'requirements': [{'requirement_id': 'denied', 'text': 'blocked'}]},
])
def test_metadata_empty_failed_or_denied_bodies_do_not_invent_returned_items(tmp_path, monkeypatch, body):
    reply, activity, _ = invoke(tmp_path, monkeypatch, body)
    assert reply['returned_count'] == 0
    assert activity['mapping_items'] == []
    assert activity['returned_content_snapshot'] is None
    assert activity['original_message_readback_count'] == 0
