import copy
import pytest
try:
    from lib import scenario_intent_atoms as atoms
except ImportError:
    atoms=None
from lib.scenario_coverage_partition import partition_snapshot
from test_scenario_coverage_partition import snapshot


def fixture(tmp_path,text='仅草稿时不要发布🙂'):
    assert atoms is not None, 'intent atom implementation missing'
    s=snapshot(tmp_path,text)
    p=partition_snapshot(s,capacity=1000)['partitions'][0]
    user=next(x for x in p['primary'] if x['role']=='user')
    ref={'span_id':user['span_id'],'start':0,'end':len(text),'quote':text}
    item={'source_refs':[ref],'kind':'constraint','authority':'user_requirement','action':'发布',
          'conditions':['仅草稿时'],'negation':True,'exceptions':[],'object_hypotheses':[],
          'time':{'event':None,'effective':None},'local_state':'expressed'}
    return s,p,{'atoms':[item],'residuals':[],'assistant_claims':[]}


def test_exact_multilingual_condition_retained_without_fact_promotion(tmp_path):
    s,p,proposal=fixture(tmp_path)
    result=atoms.validate_atom_proposal(s,p,proposal)
    assert result['errors']==[]
    assert result['atoms'][0]['source_quote']=='仅草稿时不要发布🙂'
    assert result['atoms'][0]['conditions']==['仅草稿时']
    assert result['atoms'][0]['negation'] is True
    assert result['semantic_review_status']=='not_reviewed'
    assert result['external_fact_verified'] is False


def test_cross_span_preserves_condition(tmp_path):
    s,p,proposal=fixture(tmp_path,'仅草稿时不要发布')
    user=p['primary'][0];cut=4
    left={**user,'span_id':'left','end':cut,'text':user['text'][:cut]}
    right={**user,'span_id':'right','start':cut,'text':user['text'][cut:]}
    p['primary']=[left,right,*p['primary'][1:]]
    proposal['atoms'][0]['source_refs']=[{'span_id':'left','start':0,'end':cut,'quote':'仅草稿时'},
        {'span_id':'right','start':0,'end':4,'quote':'不要发布'}]
    result=atoms.validate_atom_proposal(s,p,proposal)
    assert result['errors']==[]
    assert ''.join(r['quote'] for r in result['atoms'][0]['source_refs'])=='仅草稿时不要发布'


def test_unique_literal_selector_derives_unicode_offsets_without_model_arithmetic(tmp_path):
    s,p,proposal=fixture(tmp_path,'仅草稿时不要发布🙂')
    ref=proposal['atoms'][0]['source_refs'][0]
    ref.pop('start');ref.pop('end')
    result=atoms.validate_atom_proposal(s,p,proposal)
    assert result['errors']==[]
    bound=result['atoms'][0]['source_refs'][0]
    assert (bound['start'],bound['end'])==(0,len('仅草稿时不要发布🙂'))
    assert bound['normalized_start']==0 and bound['quote']=='仅草稿时不要发布🙂'
    assert result['semantic_review_status']=='not_reviewed'
    assert result['external_fact_verified'] is False


def test_literal_selector_retains_distinct_conditions_across_multiple_quotes(tmp_path):
    s,p,proposal=fixture(tmp_path,'Draft🙂: do not publish. 最终版可以发布。')
    span=proposal['atoms'][0]['source_refs'][0]['span_id']
    first=proposal['atoms'][0];first['source_refs']=[{'span_id':span,'quote':'Draft🙂: do not publish. '}]
    second=copy.deepcopy(first);second.update(action='发布最终版',negation=False,conditions=['最终版'])
    second['source_refs']=[{'span_id':span,'quote':'最终版可以发布。'}]
    proposal['atoms'].append(second)
    result=atoms.validate_atom_proposal(s,p,proposal)
    assert result['errors']==[]
    assert [r['source_refs'][0]['start'] for r in result['atoms']]==[0,len('Draft🙂: do not publish. ')]
    assert result['atoms'][0]['negation'] is True and result['atoms'][1]['negation'] is False


@pytest.mark.parametrize('mode',['ambiguous','explicit_wrong','one_offset','absent_quote','invented_quote'])
def test_literal_selector_never_repairs_ambiguous_or_explicitly_wrong_positions(tmp_path,mode):
    s,p,proposal=fixture(tmp_path,'不要发布。不要发布。')
    ref=proposal['atoms'][0]['source_refs'][0]
    if mode=='explicit_wrong':ref.update(start=1)
    elif mode=='one_offset':ref.pop('end')
    else:
        ref.pop('start');ref.pop('end')
        if mode=='ambiguous':ref['quote']='不要发布。'
        elif mode=='absent_quote':ref.pop('quote')
        else:ref['quote']='不要外发。'
    result=atoms.validate_atom_proposal(s,p,proposal)
    assert result['errors']
    assert result['semantic_review_status']=='not_reviewed'


@pytest.mark.parametrize('change',['quote','role','missing','duplicate','metadata'])
def test_bad_or_incomplete_mapping_never_looks_reviewed(tmp_path,change):
    s,p,proposal=fixture(tmp_path)
    if change=='quote':proposal['atoms'][0]['source_refs'][0]['quote']='意思差不多'
    if change=='role':proposal['atoms'][0]['source_refs'][0]['span_id']=p['primary'][-1]['span_id']
    if change=='missing':proposal['atoms']=[]
    if change=='duplicate':proposal['atoms']*=2
    if change=='metadata':proposal['atoms'][0]['negation']='yes'
    assert atoms.validate_atom_proposal(s,p,proposal)['errors']


def test_empty_user_span_is_not_an_intent_and_real_text_stays(tmp_path):
    s,p,proposal=fixture(tmp_path)
    p['primary'].append({**p['primary'][0],'span_id':'empty','text':'','start':0,'end':0})
    assert atoms.validate_atom_proposal(s,p,proposal)['errors']==[]


def test_plain_dictionary_cannot_bind_reviewed_leaf(tmp_path):
    s,p,proposal=fixture(tmp_path)
    result=atoms.bind_leaf_review(s,p,proposal,{'status':'reviewed','host_validated':True})
    assert result['semantic_review_status']!='reviewed'


def test_legacy_empty_optional_mapping_does_not_crash_materialization(tmp_path):
    from lib.scenario_coverage_review import LocalReview
    from lib.scenario_coverage_partition import build_requirement_catalog
    from lib.scenario_intent_ledger import materialize_intents
    s=snapshot(tmp_path,'<external_codex_apps_open_page>{"page_id":"p1"}</external_codex_apps_open_page>')
    p=partition_snapshot(s)
    empty=next(x for part in p['partitions'] for x in part['primary'] if x['role']=='user')
    receipt=LocalReview({'status':'local_reviewed','result':{'intent_mappings':[
        {'span_id':empty['span_id'],'start':0,'end':0,'kind':'question','disposition':'non_substantive'}]}})
    assert materialize_intents(s,p,build_requirement_catalog(p),[receipt])==[]
