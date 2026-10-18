import pytest
from test_scenario_intent_atoms import fixture
from lib.scenario_intent_atoms import validate_atom_proposal


@pytest.mark.parametrize('gap',['\n\n','\t',' \n  '])
def test_layout_between_exact_quotes_is_preserved_without_false_intent_gap(tmp_path,gap):
    text='先审阅。'+gap+'再输出。';s,p,proposal=fixture(tmp_path,text)
    sid=p['primary'][0]['span_id']
    proposal['atoms'][0]['source_refs']=[{'span_id':sid,'quote':'先审阅。'},{'span_id':sid,'quote':'再输出。'}]
    before=s['units'][0]['text']
    checked=validate_atom_proposal(s,p,proposal)
    assert checked['errors']==[]
    assert checked['atoms'][0]['source_quote']==text
    assert s['units'][0]['text']==before
    assert checked['semantic_review_status']=='not_reviewed'


@pytest.mark.parametrize('gap',['不要','!','，但须先确认'])
def test_unquoted_nonlayout_content_is_still_an_intent_gap(tmp_path,gap):
    s,p,proposal=fixture(tmp_path,'先审阅。'+gap+'再输出。');sid=p['primary'][0]['span_id']
    proposal['atoms'][0]['source_refs']=[{'span_id':sid,'quote':'先审阅。'},{'span_id':sid,'quote':'再输出。'}]
    assert validate_atom_proposal(s,p,proposal)['errors']==['intent_character_gap']
