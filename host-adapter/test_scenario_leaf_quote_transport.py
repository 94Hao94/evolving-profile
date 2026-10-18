from copy import deepcopy
import pytest
from lib.scenario_hierarchical_review import build_review_request


def request(text,ref):
    primary={'span_id':'raw-span','role':'assistant','sequence':3,'start':0,'end':len(text),'text':text}
    inputs={'partition':{'primary':[primary],'context_only':'前文'},
        'proposal':{'atoms':[],'residuals':[],'assistant_claims':[{'authority':'assistant_report','claim':'报告原文','source_refs':[ref]}]}}
    before=deepcopy(inputs)
    out=build_review_request('leaf',{},inputs,{'partition_input_tokens':6000,'partition_output_tokens':2000})
    assert inputs==before and out['inputs']==before
    return out


def test_leaf_transport_references_unique_exact_quote_without_repeating_source():
    text='仅为助手自述，未核验外部文件🙂。'*30
    ref={'span_id':'raw-span','quote':text}
    out=request(text,ref);wire=out['model_request']['inputs'];encoded=wire['proposal']['assistant_claims'][0]['source_refs'][0]
    assert encoded=={'span_id':'r0','source_selection':'entire_span'}
    assert wire['partition']['primary'][0]['verbatim_transport_fragment']==text
    assert ref=={'span_id':'raw-span','quote':text}


@pytest.mark.parametrize('mode',['wrong_end','changed_quote','repeated_implicit'])
def test_leaf_transport_never_repairs_bad_or_ambiguous_model_quote_positions(mode):
    text='不要发布🙂。不要发布🙂。';ref={'span_id':'raw-span','quote':'不要发布🙂。'}
    if mode=='wrong_end':ref.update(start=0,end=1)
    if mode=='changed_quote':ref.update(quote='应当发布',start=0,end=3)
    out=request(text,ref);encoded=out['model_request']['inputs']['proposal']['assistant_claims'][0]['source_refs'][0]
    assert encoded['quote']==ref['quote'] and 'quote_source_span' not in encoded


def test_model_cannot_supply_the_host_owned_quote_transport_marker():
    text='不要发布。可以发布。';ref={'span_id':'raw-span','quote':'不要发布。','quote_source_span':[5,10]}
    out=request(text,ref);encoded=out['model_request']['inputs']['proposal']['assistant_claims'][0]['source_refs'][0]
    assert encoded['verbatim_quote']=='不要发布。' and 'quote_source_span' not in encoded
    assert out['inputs']['proposal']['assistant_claims'][0]['source_refs'][0]['quote_source_span']==[5,10]


def test_host_transport_marker_in_model_proposal_is_rejected_before_leaf(tmp_path):
    from test_scenario_intent_atoms import fixture
    from lib.scenario_intent_atoms import validate_atom_proposal
    s,p,proposal=fixture(tmp_path,'不要发布。可以发布。')
    proposal['atoms'][0]['source_refs'][0]['quote_source_span']=[5,10]
    assert validate_atom_proposal(s,p,proposal)['errors']==['atom_reserved_transport_field']


def test_full_explicit_quote_does_not_ask_semantic_model_to_recount_unicode():
    text='报告未核验🙂，不能升级为事实。'
    out=request(text,{'span_id':'raw-span','quote':text,'start':0,'end':len(text)})
    ref=out['model_request']['inputs']['proposal']['assistant_claims'][0]['source_refs'][0]
    assert ref=={'span_id':'r0','source_selection':'entire_span'}
