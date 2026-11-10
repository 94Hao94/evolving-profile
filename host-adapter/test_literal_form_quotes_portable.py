import pytest

from lib import scenario_state_v3
from lib.scenario_review_catalog import review_source_layer


@pytest.mark.parametrize("body", [
    '[{"question":"Which format?","answer":"Use two characters"}]',
    'not JSON',
    '[{"question":"Q","answer":"A","extra":1}]',
    '[{"question":"Q","answer":"A","answer":"B"}]',
])
def test_unverified_form_stays_literal_and_offers_exact_whole_clause(body, monkeypatch):
    raw = '<send_user_message_question_reply>\n' + body + '\n</send_user_message_question_reply>'
    def forbidden(*args):
        raise AssertionError("Literal source must not be decoded into synthetic Q/A")
    monkeypatch.setattr(scenario_state_v3, 'parse_form_reply', forbidden)
    assert scenario_state_v3.whole_user_clauses(raw) == [' '.join(raw.split())]
    layer = review_source_layer({'messages': [
        {'evidence_id': 'u1', 'role': 'user', 'text': raw, 'form_reply_unverified': True},
    ]})
    quotes = [q for q in layer['source_quotes'] if q['whole_clause']]
    assert quotes and any(q['source_quote'] == raw for q in quotes)
    for quote in quotes:
        witness = next(q for q in layer['transport_source_quotes'] if q['ref'] == quote['ref'])
        start, end = witness['source_span']
        assert raw[start:end] == quote['source_quote']


def test_proven_answer_text_and_normal_multi_clause_input_remain_literal():
    answer = 'Use two characters'
    assert scenario_state_v3.whole_user_clauses(answer) == [answer]
    raw = 'Keep the title.\n\nPreserve all paragraphs.'
    for clause in scenario_state_v3.whole_user_clauses(raw):
        assert clause in ' '.join(raw.split())
