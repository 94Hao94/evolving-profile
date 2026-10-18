"""Scenario gating preserves the evidence plane of raw process candidates."""
import pytest

from lib.scenario_gate import decide_scenario_summary


def process(identity='p1', context=None, **values):
    return {'process_memory_id': identity, 'primary_context': context or {}, **values}


def test_raw_process_candidates_deduplicate_and_keep_exact_turn_navigation():
    rows = [process(context={'session_id': 's1', 'turn_id': 't1'}),
            process(context={'session_id': 's1', 'turn_id': 't1'}),
            process('p2', {'session_id': 's2', 'turn_id': 't2'})]

    result = decide_scenario_summary('执行背景', rows, unresolved_slots=['历史背景'])

    assert result['candidate_count'] == 3
    assert result['deduplicated_count'] == 2
    assert result['decision'] == 'compact'
    assert result['session_groups'] == {'s1': 1, 's2': 1}
    assert result['source_scenario_ids'] == ['session:s1/turn/t1', 'session:s2/turn/t2']


def test_process_and_bank_identifiers_have_separate_deduplication_namespaces():
    rows = [process('same', {'session_id': 'process-session'}),
            {'id': 'same', 'session_ids': ['bank-session']},
            {'canonical_memory_id': 'same', 'id': 'bank-alias', 'session_ids': ['bank-session']}]

    result = decide_scenario_summary('执行背景', rows)

    assert result['deduplicated_count'] == 2
    assert result['session_groups'] == {'process-session': 1, 'bank-session': 1}


def test_process_cwd_and_project_path_do_not_become_project_identity():
    rows = [process('p1', {'project': '/same/cwd', 'cwd': '/same/cwd'}),
            process('p2', {'project': '/same/cwd', 'cwd': '/same/cwd'})]

    result = decide_scenario_summary('执行背景', rows, unresolved_slots=['对象范围'])

    assert result['deduplicated_count'] == 2
    assert result['project_count'] == 0
    assert result['session_count'] == 0
    assert result['decision'] == 'unavailable_no_scope_link'
    assert result['source_scenario_ids'] == []


@pytest.mark.parametrize('context', [None, 'not-a-mapping', [], 9, {'session_id': ['s1'], 'turn_id': {'x': 't1'}}])
def test_malformed_process_context_does_not_crash_or_manufacture_scope(context):
    row = {'process_memory_id': 'p1', 'primary_context': context}

    result = decide_scenario_summary('执行背景', [row])

    assert result['deduplicated_count'] == 1
    assert result['session_count'] == 0
    assert result['decision'] == 'unavailable_no_scope_link'


def test_current_context_sufficient_keeps_counts_for_process_candidates():
    rows = [process(context={'session_id': 's1'}), process(context={'session_id': 's1'})]

    result = decide_scenario_summary('执行背景', rows, current_context_sufficient=True)

    assert result['candidate_count'] == 2
    assert result['deduplicated_count'] == 1
    assert result['decision'] == 'none'
    assert result['reason_codes'] == ['current_context_sufficient']
    assert result['recommended_route'] == 'none'


def test_factual_process_candidates_use_process_readback_even_with_generic_id():
    rows = [process(context={'session_id': 's1'}, id='also-an-agent-id')]

    result = decide_scenario_summary('核对执行状态和版本', rows, unresolved_slots=['状态'])

    assert result['deduplicated_count'] == 1
    assert result['recommended_route'] == 'read_agent_process_memory'


def test_factual_mixed_evidence_planes_require_agent_choice():
    rows = [process(context={'session_id': 's1'}), {'id': 'm1', 'session_ids': ['s1']}]

    result = decide_scenario_summary('核对执行状态和版本', rows, unresolved_slots=['状态'])

    assert result['deduplicated_count'] == 2
    assert result['recommended_route'] == 'agent_decides'


def test_factual_bank_candidates_keep_bank_read_source_route_and_dedup():
    rows = [{'id': 'm1', 'metadata': {'session_id': 's1'}},
            {'canonical_memory_id': 'm1', 'id': 'alias', 'metadata': {'session_id': 's1'}}]

    result = decide_scenario_summary('核对金额和版本', rows, unresolved_slots=['金额'])

    assert result['deduplicated_count'] == 1
    assert result['recommended_route'] == 'read_source'


def test_explicit_process_project_key_is_only_navigation():
    result = decide_scenario_summary('执行背景', [process(metadata={'project_key': 'explicit-key'})],
                                     unresolved_slots=['对象范围'])

    assert result['deduplicated_count'] == 1
    assert result['project_groups'] == {'explicit-key': 1}
    assert result['evidence_role'] == 'scenario_explanation_only'
    assert result['decision'] == 'compact'


def test_raw_process_project_audit_needs_explicit_project_scope():
    rows = [process(context={'session_id': 's1', 'project': '/shared/cwd', 'cwd': '/shared/cwd'})]

    result = decide_scenario_summary('整个项目的原始会话全文', rows,
                                     unresolved_slots=['整个项目的原始会话'])

    assert result['project_count'] == 0
    assert result['session_count'] == 1
    assert result['recommended_route'] == 'search_scenario_summary'


def test_pure_bank_project_audit_keeps_existing_route_without_project_key():
    result = decide_scenario_summary('整个项目的原始会话全文',
                                     [{'id': 'm1', 'metadata': {'session_id': 's1'}}])

    assert result['project_count'] == 0
    assert result['recommended_route'] == 'audit_project_sessions'
