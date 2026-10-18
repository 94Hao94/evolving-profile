import json

import pytest

from test_source_authority_publication import _candidate, _source
from observation_publish import build_observation_proposal, publication_review


def source(document, quote, message, session='lecture-session', turn='recorded-turn', task_id=None):
    # Rebuild authoritative attribution after assigning native task metadata.
    from evolving_profile_api.engine.retain.source_attribution import verify_attribution
    item = _source(document, quote, message)
    rows = json.loads(item['source_text'])
    rows[0]['source_record'].update(session_id=session, turn_id=turn)
    if task_id: rows[0]['source_record']['task_id'] = task_id
    item['source_text'] = json.dumps(rows, ensure_ascii=False)
    item['memory_metadata'] = verify_attribution(item['source_text'],
        {'source_role': 'user', 'source_quote': quote, 'source_message_index': 0},
        {'source_attribution_required': 'role_quote_v1'})[2]
    return item


def test_two_messages_same_lecture_are_usable_local_evidence_not_cross_task_pattern():
    rows = [source('a', '本讲座要保留提高下限与扩大上限差距。', 'msg-a'),
            source('b', '强调有没有问题、问题多不多、会不会问。', 'msg-b')]
    proposal = build_observation_proposal(_candidate(), rows, 'bank')
    assert proposal['nature'] == 'task_local'
    assert proposal['scope_level'] == 'task'
    assert proposal['scope']['session_ids'] == ['lecture-session']
    assert proposal['support_count'] == 1
    assert len(proposal['evidence_refs']) == 2
    assert proposal['confidence_inputs']['independent_original_user_origins'] == 2
    assert proposal['confidence_inputs']['independent_task_contexts'] == 1


def test_different_turns_in_same_task_do_not_certify_cross_context_stability():
    proposal = build_observation_proposal(_candidate(), [source('a', '保留核心论点。', 'a'),
        source('b', '继续保留核心论点。', 'b', turn='next-turn')], 'bank')
    assert proposal['nature'] == 'task_local'


def test_independent_task_contexts_can_support_pattern():
    proposal = build_observation_proposal(_candidate(), [source('a', '保留核心论点。', 'a'),
        source('b', '保留核心论点。', 'b', session='independent-task')], 'bank')
    assert proposal['nature'] == 'inferred_pattern'
    assert proposal['support_count'] == 2


@pytest.mark.parametrize('quote', ['以后所有回答都先说明结论。', 'From now on, always lead with the conclusion.'])
def test_single_explicit_enduring_user_rule_can_be_global(quote):
    candidate = {**_candidate(), 'nature': 'explicit_requirement', 'scope_level': 'global'}
    proposal = build_observation_proposal(candidate, [source('a', quote, 'a')], 'bank')
    assert proposal['nature'] == 'explicit_requirement'
    assert proposal['scope_level'] == 'global'
    assert proposal['scope'].get('session_ids', []) == []


def test_classifier_global_label_cannot_make_current_lecture_request_enduring():
    candidate = {**_candidate(), 'nature': 'explicit_requirement', 'scope_level': 'global'}
    proposal = build_observation_proposal(candidate, [source('a', '本讲座必须保留核心论点。', 'a')], 'bank')
    assert proposal['nature'] == 'task_local'


def test_publication_review_rejects_legacy_same_task_broad_proposal():
    proposal = build_observation_proposal(_candidate(), [source('a', '保留核心论点。', 'a'),
        source('b', '继续保留核心论点。', 'b')], 'bank')
    proposal.update(nature='inferred_pattern', scope_level='global', support_count=2)
    proposal['scope'].pop('session_ids', None)
    semantic = {'id': 'c1', 'support': 'supported', 'scope_ok': True,
        'conditions_preserved': True, 'source_role_ok': True, 'hypothetical_only': False,
        'conflicts': [], 'evidence': [{'memory_id': r['memory_id'], 'quote': r['quote']}
                                     for r in proposal['evidence_refs']]}
    with pytest.raises(ValueError, match='independent_task'):
        publication_review(proposal, semantic_review=semantic)


def test_selector_enforces_native_session_scope_even_when_words_match():
    from test_recall_first import Repo, unit, request
    from selector import get_task_guidance
    row = unit('lecture-local', '讲座必须保留核心论点。', '讲座修改', 'communication')
    row['scope'] = {'session_ids': ['lecture-session']}
    req = request('讲座修改，保留核心论点。')
    assert get_task_guidance(Repo([row]), req)['included'] == []
    req['task']['session_id'] = 'other-session'
    assert get_task_guidance(Repo([row]), req)['included'] == []
    req['task']['session_id'] = 'lecture-session'
    assert [u['id'] for u in get_task_guidance(Repo([row]), req)['included']] == ['lecture-local']


def test_task_local_scope_cannot_be_rebound_to_an_unrelated_session():
    from observation_publish import validate_task_scope
    proposal = build_observation_proposal(_candidate(), [source('a', '本讲座保留核心论点。', 'a')], 'bank')
    proposal['scope']['session_ids'] = ['different-task']
    with pytest.raises(ValueError, match='source_context_mismatch'):
        validate_task_scope(proposal)


def test_missing_task_id_in_known_session_cannot_create_another_vote():
    from observation_publish import validate_task_scope
    proposal = build_observation_proposal(_candidate(), [
        source('a', '本讲座保留核心论点。', 'a', task_id='native-task'),
        source('b', '本讲座补足提问三层。', 'b')], 'bank')
    assert proposal['nature'] == 'task_local'
    assert proposal['support_count'] == 1
    assert proposal['scope']['task_ids'] == ['native-task']
    legacy = {**proposal, 'nature': 'inferred_pattern', 'scope_level': 'global', 'support_count': 2}
    with pytest.raises(ValueError, match='independent_task'):
        validate_task_scope(legacy)


def test_positively_different_native_tasks_in_one_session_remain_independent():
    proposal = build_observation_proposal(_candidate(), [
        source('a', '保留核心论点。', 'a', task_id='native-task-a'),
        source('b', '保留核心论点。', 'b', task_id='native-task-b'),
        source('c', '补足论证。', 'c')], 'bank')
    assert proposal['nature'] == 'inferred_pattern'
    assert proposal['support_count'] == 2
