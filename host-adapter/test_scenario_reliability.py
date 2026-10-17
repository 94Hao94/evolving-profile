"""Source-shape and reference regressions from the October scenario audit."""
import copy

import pytest

from lib.scenario_model import deterministic_source_state_draft
from lib.scenario_review_catalog import review_catalog, catalog_sha, expand_review_choices
from lib.scenario_state_v3 import validate_state_draft, USER_CLAIM_PROTOCOL
from test_scenario_state_v3 import source, claim
from test_memory_recovery_scenario import fixture


@pytest.mark.parametrize('bad', [None, [], 'state', {'constraints': []}])
def test_malformed_state_has_controlled_contract_diagnostics(bad):
    original = source([('user', 'Prepare the report.'), ('assistant', 'Reported; unverified.')])
    with pytest.raises(ValueError, match='^scenario_state_invalid$'):
        validate_state_draft(original, bad, model='fixture')


def test_state_validation_does_not_modify_rejected_provider_payload():
    original = source([('user', '不要公开凭据。'), ('assistant', 'Reported; unverified.')])
    state = {'subject': claim('Report', 'id1'), 'goal': claim('Report', 'id1'),
             'phase': 'invalid', 'constraints': [claim('不要公开凭据。', 'id1')],
             'corrections': [], 'assistant_reports': [], 'unresolved': []}
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        validate_state_draft(original, state, model='fixture')
    assert state == before


def test_fallback_preserves_more_than_one_hundred_short_conditions_without_partial_slicing():
    conditions = [f'必须保留编号{i}的用户条件。' for i in range(106)]
    original = source([('user', ''.join(conditions)), ('assistant', 'Recorded; unverified.')])
    draft = deterministic_source_state_draft(original)
    assert all(text in draft['summaries']['full'] for text in conditions)
    assert draft['review_status'] == 'pending_independent_review'
    assert draft['source_linked_fallback']['semantic_completeness_proven'] is False
    assert draft['source_linked_fallback']['provider_verdict_required'] is True


def test_fallback_keeps_latest_user_request_unresolved_after_older_answer():
    original = source([('user', 'Prepare the report.'), ('assistant', 'I answered the earlier question.'),
                       ('user', 'Now correct the source binding.')])
    draft = deterministic_source_state_draft(original)
    assert draft['state']['phase'] == 'requested'
    assert draft['state']['unresolved'] == [claim('Now correct the source binding.', 'id3')]


@pytest.mark.parametrize('text', ['只用 imagegen  做完整页！', 'Keep the original scope.\nDo not publish keys.',
                                 'Use  version 3.7; keep the  1.5 second timeout.'])
def test_review_catalog_every_quote_is_exact_contiguous_original_text(tmp_path, text):
    _, _, original, bundle, _ = fixture(tmp_path)
    original['messages'][0]['text'] = text
    catalog = review_catalog(original, bundle)
    quotes = [q for q in catalog['source_quotes'] if q['message_ref'] == 'm1']
    assert len(quotes) >= 1
    assert all(q['source_quote'] in text for q in quotes)
    assert any(q['source_quote'] == text for q in quotes)


def test_selected_later_exact_quote_resolves_superseding_ref_without_inventing_relation(tmp_path):
    _, _, original, bundle, _ = fixture(tmp_path)
    catalog = review_catalog(original, bundle)
    value = {'selection_catalog_sha256': catalog_sha(catalog), 'user_intent_coverage': [
        {'message_ref': 'm1', 'intents': [{'kind': 'request', 'source_quote_ref': 'm1q1',
          'disposition': 'superseded', 'superseding_quote_ref': 'm3q1', 'field_links': []}]}]}
    expanded, used = expand_review_choices(value, catalog)
    item = expanded['user_intent_coverage'][0]['intents'][0]
    assert used and item['superseded_by_ref'] == 'm3'
    assert item['superseding_quote'] == original['messages'][2]['text']
    assert item['disposition'] == 'superseded'
    assert value['user_intent_coverage'][0]['intents'][0].get('superseded_by_ref') is None


@pytest.mark.parametrize('target, explicit', [('m1q1', None), ('m1q1', 'm1'), ('m3q1', 'm1'),
                                            ('missing', None)])
def test_superseding_selection_rejects_self_earlier_wrong_and_unknown_sources(tmp_path, target, explicit):
    _, _, original, bundle, _ = fixture(tmp_path)
    catalog = review_catalog(original, bundle)
    item = {'kind': 'request', 'source_quote_ref': 'm1q1', 'disposition': 'superseded',
            'superseding_quote_ref': target, 'field_links': []}
    if explicit is not None:
        item['superseded_by_ref'] = explicit
    value = {'selection_catalog_sha256': catalog_sha(catalog),
             'user_intent_coverage': [{'message_ref': 'm1', 'intents': [item]}]}
    with pytest.raises(ValueError, match='automated_source_coverage_incomplete'):
        expand_review_choices(value, catalog)


def test_wrong_source_revision_cannot_be_hidden_by_deterministic_fallback():
    import io
    import json
    from lib.scenario_model import request_episode_bundle
    original = source([('user', 'Prepare the report.'), ('assistant', 'Reported; unverified.')])
    def wrong_source(request, **_):
        result = {'source_revision': 'a-stale-source', 'state': {}}
        return io.BytesIO(json.dumps({'choices': [{'finish_reason': 'stop',
                            'message': {'content': json.dumps(result)}}]}).encode())
    with pytest.raises(ValueError, match='scenario_source_revision_mismatch'):
        request_episode_bundle(original, base_url='https://fixture.invalid', api_key='test',
                               model='fixture', opener=wrong_source)


def test_non_object_provider_state_uses_bounded_structure_repair():
    import io
    import json
    from lib.scenario_model import request_session_state_draft
    original = source([('user', 'Prepare the report.'), ('assistant', 'Reported; unverified.')])
    replies = [[], {'source_revision': original['source_revision'], 'state': {
        'subject': claim('Report', 'id1'), 'goal': claim('Prepare report', 'id1'),
        'phase': 'assistant_reported', 'constraints': [], 'corrections': [],
        'assistant_reports': [claim('Reported; unverified.', 'id2')], 'unresolved': []}}]
    def reply(request, **_):
        result = replies.pop(0)
        return io.BytesIO(json.dumps({'choices': [{'finish_reason': 'stop',
                            'message': {'content': json.dumps(result)}}]}).encode())
    draft = request_session_state_draft(original, base_url='https://fixture.invalid', api_key='test',
                                        model='fixture', opener=reply)
    assert draft['review_status'] == 'pending_independent_review'
    assert draft['state']['goal']['text'] == 'Prepare report'


def test_raw_exact_whitespace_quote_keeps_strict_constraint_mapping(tmp_path):
    from lib.memory_recovery_scenario import validate_user_intent_coverage, CoverageError
    from test_memory_recovery_scenario import intent_manifest
    _, _, original, bundle, _ = fixture(tmp_path)
    original['messages'][0]['text'] = 'Only  use source-linked evidence.'
    state = bundle['episodes'][0]['draft']['state']
    state['constraints'] = [claim('Only use source-linked evidence.', original['messages'][0]['evidence_id'])]
    bundle['episodes'][0]['draft']['summaries']['full'] += '\nOnly use source-linked evidence.'
    manifest = intent_manifest(original, bundle)
    item = manifest[0]['intents'][0]
    item.update(kind='constraint', field_links=[{'episode_ref': 'e1', 'state_path': 'constraints/0/text',
        'field_quote': 'Only use source-linked evidence.', 'summary_paths': ['full']}])
    assert validate_user_intent_coverage(original, bundle, manifest)[0]['intents'][0]['source_quote'] == 'Only  use source-linked evidence.'
    item['source_quote'] = 'Only use source-linked evidence.'
    with pytest.raises(CoverageError, match='automated_source_coverage_incomplete'):
        validate_user_intent_coverage(original, bundle, manifest)


def test_standard_navigation_selects_whole_conditions_while_full_retains_every_condition():
    first='Only after approval, '+('preserve the source scope, '*100)+'stop.'
    second='When a new source arrives, '+('keep its original provenance, '*100)+'review.'
    original=source([('user',first),('assistant','Earlier reply.'),('user',second),('assistant','Reported; unverified.')])
    state={'subject':claim('Source review','id1'),'goal':claim('Review revised source','id3'),
           'phase':'assistant_reported','constraints':[claim(first,'id1'),claim(second,'id3')],
           'corrections':[],'assistant_reports':[claim('Reported; unverified.','id4')],'unresolved':[]}
    draft=validate_state_draft(original,state,model='fixture',user_claim_protocol=USER_CLAIM_PROTOCOL)
    assert first in draft['summaries']['full'] and second in draft['summaries']['full']
    assert len(draft['summaries']['standard'])<=5000
    assert first in draft['summaries']['standard']
    assert second not in draft['summaries']['standard']


def test_fallback_compact_keeps_pending_status_when_source_bookends_are_long():
    original=source([('user','Prepare '+('a detailed report '*20)),('assistant','Earlier reply.'),
                     ('user','Now correct '+('the source binding '*20))])
    draft=deterministic_source_state_draft(original)
    assert draft['state']['phase']=='requested'
    assert draft['state']['unresolved'][0]['message_ids']==['id3']
    assert '待核' in draft['summaries']['compact']
    assert len(draft['summaries']['compact'])<=500
