from copy import deepcopy
import pytest
from test_scenario_intent_atoms import fixture
from lib.scenario_intent_atoms import validate_atom_proposal
from lib.scenario_hierarchical_review import build_review_request


def test_whole_span_selection_resolves_original_unicode_html_and_layout_without_model_copy(tmp_path):
    text='<p>仅草稿🙂，不要发布。</p>\n\n<p>保留原文。</p>';s,p,proposal=fixture(tmp_path,text)
    sid=p['primary'][0]['span_id'];proposal['atoms'][0]['source_refs']=[{'span_id':sid,'source_selection':'entire_span'}]
    before=deepcopy(proposal);out=validate_atom_proposal(s,p,proposal)
    assert out['errors']==[] and out['atoms'][0]['source_quote']==text
    assert out['atoms'][0]['source_refs'][0]['offset_binding']=='host_selected_entire_span'
    assert out['semantic_review_status']=='not_reviewed' and proposal==before
    req=build_review_request('leaf',{}, {'partition':p,'proposal':proposal},{'partition_input_tokens':12000,'partition_output_tokens':2000})
    ref=req['model_request']['inputs']['proposal']['atoms'][0]['source_refs'][0]
    assert ref['source_selection']=='entire_span' and 'quote_source_span' not in ref
    assert req['inputs']['proposal']==before


@pytest.mark.parametrize('extra',[{'quote':'fake'},{'start':0},{'end':3},{'source_selection':'guess'}])
def test_entire_span_selector_cannot_override_quote_or_one_sided_positions(tmp_path,extra):
    s,p,proposal=fixture(tmp_path);sid=p['primary'][0]['span_id']
    proposal['atoms'][0]['source_refs']=[{'span_id':sid,'source_selection':'entire_span',**extra}]
    assert validate_atom_proposal(s,p,proposal)['errors']==['atom_source_selector_invalid']
