"""Published 5.1 budgets must not silently regress to the old deployment."""
import pytest
from lib.context_summary import bounded_summary


@pytest.mark.parametrize('tier,text',[
    ('standard','保留完整条件。'*300),
    ('full','保留完整条件。'*900),
])
def test_content_beyond_old_summary_caps_is_preserved(tier,text):
    rendered,receipt=bounded_summary(text,'session',tier)
    assert rendered==text
    assert receipt['truncated'] is False


@pytest.mark.parametrize('tier,text',[
    ('standard','条件。'*1800),
    ('full','条件。'*4300),
])
def test_current_summary_caps_still_reject_excess(tier,text):
    rendered,receipt=bounded_summary(text,'session',tier)
    assert receipt['truncated'] is True
    assert len(rendered)<len(text)
