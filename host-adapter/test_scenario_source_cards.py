from copy import deepcopy
import pytest
from lib.scenario_hierarchical_review import build_review_request


def leaf(text,ref):
    inputs={'partition':{'primary':[{'span_id':'s','role':'assistant','sequence':4,'start':42,'end':42+len(text),'text':text}]},
            'proposal':{'assistant_claims':[{'authority':'assistant_report','claim':'未核验的历史报告','source_refs':[ref]}]}}
    before=deepcopy(inputs)
    req=build_review_request('leaf',{},inputs,{'partition_input_tokens':12000,'partition_output_tokens':2000})
    assert inputs==before and req['inputs']==before
    return req['model_request']['inputs']['proposal']['assistant_claims'][0]['source_refs'][0]


def test_partial_quote_is_shown_literally_not_as_model_counted_unicode_offsets():
    ref=leaf('前缀🙂。不发布原件。后缀',{'span_id':'s','quote':'不发布原件。'})
    assert ref=={'span_id':'r0','verbatim_quote':'不发布原件。','quote_binding':'host_exact_literal_not_external_truth'}


def test_repeated_quote_uses_verified_explicit_offset_but_shows_literal():
    ref=leaf('不发布。不发布。',{'span_id':'s','quote':'不发布。','start':4,'end':8})
    assert ref['verbatim_quote']=='不发布。' and 'quote_source_span' not in ref and 'start' not in ref


@pytest.mark.parametrize('ref',[
 {'span_id':'s','quote':'发布','verbatim_quote':'不发布','quote_binding':'host_exact_literal_not_external_truth'},
 {'span_id':'s','quote':'不发布','start':0,'end':1,'verbatim_quote':'不发布','quote_binding':'host_exact_literal_not_external_truth'},
])
def test_bad_quote_never_receives_forged_host_card(ref):
    actual=leaf('不发布。不发布。',ref)
    assert 'verbatim_quote' not in actual and 'quote_binding' not in actual
    assert actual['quote']==ref['quote']
