from copy import deepcopy
import pytest
from test_scenario_intent_atoms import fixture
from lib.scenario_intent_atoms import validate_atom_proposal


def test_shared_source_keeps_distinct_intents_but_not_duplicate_meanings(tmp_path):
    snap,part,proposal=fixture(tmp_path,'只生成草稿，不得发布。')
    proposal['atoms'][0]['source_refs']=[{'span_id':part['primary'][0]['span_id'],'source_selection':'entire_span'}]
    second=deepcopy(proposal['atoms'][0]);second.update(action='禁止发布',negation=True)
    proposal['atoms'].append(second)
    result=validate_atom_proposal(snap,part,proposal,identity_version='source_semantics.v2')
    assert result['errors']==[] and len(result['atoms'])==2
    a,b=result['atoms'];assert a['source_group_id']==b['source_group_id'] and a['stable_id']!=b['stable_id']
    assert validate_atom_proposal(snap,part,proposal)['errors']==['duplicate_atom']
    proposal['atoms'][1]=deepcopy(proposal['atoms'][0])
    assert validate_atom_proposal(snap,part,proposal,identity_version='source_semantics.v2')['errors']==['duplicate_atom']


def selection_request():
    return {'catalog':[{'id':'s0','source_id':'first','kind':'span'},{'id':'s1','source_id':'second','kind':'span'},
       {'id':'p0','source_id':'page','kind':'source_page'}],
       'inputs':{'partition':{'primary':[{'span_id':'first','text':'仅检查🙂。','role':'user'},
                                        {'span_id':'second','text':'Do not publish.','role':'user'}]}}}


def test_card_decode_is_lossless_and_never_mutates_model_response():
    from lib.scenario_hierarchical_selection import decode_selection_proposal
    raw={'atoms':[{'source_cards':['s0','s1'],'kind':'constraint','authority':'user_requirement','action':'inspect',
         'conditions':[],'negation':True,'exceptions':[],'time':{},'object_hypotheses':[]}],'residuals':[],'assistant_claims':[]}
    before=deepcopy(raw);value=decode_selection_proposal(selection_request(),raw)
    assert value['atoms'][0]['source_refs']==[{'span_id':'first','source_selection':'entire_span'},{'span_id':'second','source_selection':'entire_span'}]
    assert 'source_cards' not in value['atoms'][0] and raw==before


@pytest.mark.parametrize('cards',[[],['unknown'],['p0'],['s0','s0'],['s1','s0'],[1]])
def test_invalid_card_choice_never_gains_a_source(cards):
    from lib.scenario_hierarchical_selection import decode_selection_proposal
    raw={'atoms':[{'source_cards':cards,'action':'x'}],'residuals':[],'assistant_claims':[]}
    with pytest.raises(ValueError,match='^selection_card_invalid$'):decode_selection_proposal(selection_request(),raw)


def test_model_cannot_mix_freehand_refs_or_forge_host_identity():
    from lib.scenario_hierarchical_selection import decode_selection_proposal
    for extra in [{'source_refs':[]},{'stable_id':'mine'},{'host_validated':True},{'quote':'invented'}]:
        raw={'atoms':[{'source_cards':['s0'],'action':'x',**extra}],'residuals':[],'assistant_claims':[]}
        with pytest.raises(ValueError,match='^selection_fields_invalid$'):decode_selection_proposal(selection_request(),raw)


def test_versioned_wire_sends_source_once_and_uses_typed_aliases():
    from lib.scenario_hierarchical_review import build_review_request,expand_selected_aliases
    inputs=selection_request()['inputs'];before=deepcopy(inputs)
    req=build_review_request('extract',{'wire_contract':'source-selection.v2'},inputs,{'partition_input_tokens':12000,'partition_output_tokens':2000})
    data=req['model_request']['inputs']
    assert data['source_cards'][0]['card_id']=='s0' and data['source_cards'][0]['text']=='仅检查🙂。'
    assert 'text' not in data['partition']['primary'][0]
    assert req['inputs']==before
    selected={'atoms':[{'source_cards':['s0'],'action':'inspect'}],'residuals':[],'assistant_claims':[]}
    assert expand_selected_aliases(selected,req)['atoms'][0]['source_refs']==[{'span_id':'first','source_selection':'entire_span'}]


def test_versioned_leaf_uses_card_references_without_duplicating_verbatim_report():
    from lib.scenario_hierarchical_review import build_review_request
    text='我报告导出失败。'
    inputs={'partition':{'primary':[{'span_id':'s','role':'assistant','text':text}]},
      'proposal':{'atoms':[],'residuals':[],'assistant_claims':[{'authority':'assistant_report','claim':text,
         'source_refs':[{'span_id':'s','source_selection':'entire_span'}]}]}}
    req=build_review_request('leaf',{'wire_contract':'source-selection.v2'},inputs,{'partition_input_tokens':12000,'partition_output_tokens':2000})
    row=req['model_request']['inputs']['proposal']['assistant_claims'][0]
    assert row['source_cards']==['s0'] and row['reported_statement_cards']==['s0']
    assert 'reported_statement' not in row and 'source_refs' not in row
    assert req['inputs']==inputs


def test_missing_v2_schema_cannot_mask_an_explicit_producer_veto(tmp_path):
    from lib.scenario_hierarchical_review import build_review_request,execute_review
    from test_scenario_hierarchical_review import budget
    req=build_review_request('extract',{'wire_contract':'source-selection.v2'},selection_request()['inputs'],{'partition_input_tokens':12000,'partition_output_tokens':2000})
    response={'result':{'accept':False,'proposal':{'atoms':[],'residuals':[],'assistant_claims':[]}},'usage':{'total_tokens':10}}
    out=execute_review(req,lambda _:response,budget(tmp_path),source_current=lambda:True,authorize_request=None)
    assert out['status']=='rejected' and out['reason']=='semantic_rejected'


def test_v2_leaf_cannot_use_legacy_positive_booleans_as_scope_evidence(tmp_path):
    from lib.scenario_hierarchical_review import build_review_request,execute_review
    from test_scenario_hierarchical_review import budget,accepted
    req=build_review_request('leaf',{'wire_contract':'source-selection.v2'},selection_request()['inputs'],{'partition_input_tokens':12000,'partition_output_tokens':2000})
    result=execute_review(req,accepted,budget(tmp_path),source_current=lambda:True,authorize_request=None)
    assert result['status']=='rejected' and result['reason']=='judgment_schema_invalid'


def test_unknown_declared_wire_version_never_downgrades_to_legacy():
    from lib.scenario_hierarchical_review import build_review_request
    with pytest.raises(ValueError,match='^selection_schema_invalid$'):
        build_review_request('extract',{'wire_contract':'unknown-future'},selection_request()['inputs'],{'partition_input_tokens':12000,'partition_output_tokens':2000})


def test_real_pipeline_shared_cards_are_independently_reviewed_and_cached(tmp_path):
    from lib.scenario_coverage_partition import partition_snapshot
    from lib.scenario_coverage_incremental import process_coverage_job
    from lib.scenario_coverage_store import CoverageStore
    from lib.scenario_coverage_contract import validate_settings
    from lib.scenario_hierarchical_store import HierarchicalStore
    from test_scenario_hierarchical_end_to_end import controlled
    from test_scenario_review_partial import run
    from test_scenario_hierarchical_review import budget
    from test_scenario_source_codec import source
    from test_scenario_coverage_incremental import job
    root,_,_=source(tmp_path,text='只检查草稿，不要发布。');state=tmp_path/'state'
    value=process_coverage_job(job(),root,{},store_root=state)
    s=CoverageStore(state/'coverage.sqlite3').read(value['snapshot_id']);parts=partition_snapshot(s,capacity=2000)
    settings=validate_settings({'mode':'assisted','model_trial':True,'review_protocol':'hierarchical_review.v1'})
    calls=[];base=controlled(calls);b=budget(tmp_path/'budget',requests=10)
    def provider(req):
        out=base(req)
        if req['stage']=='extract':
            row=deepcopy(out['result']['proposal']['items'][0]);row.update(action='发布',negation=True)
            out['result']['proposal']['items'].append(row)
        return out
    first=run(state,s,parts,settings,b,provider)
    assert first['status']=='scope_reviewed' and first['atom_count']==2
    graph=HierarchicalStore(state/'hierarchical/graphs.sqlite3',readonly=True).load_current(s['scope'],s['permission'])['graph']
    a,z=graph['atoms'];assert a['source_group_id']==z['source_group_id'] and a['atom_id']!=z['atom_id']
    assert a['source_quote']==z['source_quote']=='只检查草稿，不要发布。'
    spent=b.status()['requests_used'];again=run(state,s,parts,settings,b,provider)
    assert again['model_calls']==0 and b.status()['requests_used']==spent
def test_empty_transport_cards_are_not_presented_as_selectable_sources():
    from lib.scenario_hierarchical_review import build_review_request
    inputs={'partition':{'primary':[{'span_id':'empty','role':'user','text':''},
        {'span_id':'actual','role':'user','text':'不要发布。🙂'}]}}
    req=build_review_request('extract',{'wire_contract':'source-selection.v2'},inputs,
        {'partition_input_tokens':12000,'partition_output_tokens':2000})
    assert req['inputs']==inputs
    assert [c['text'] for c in req['model_request']['inputs']['source_cards']]==['不要发布。🙂']
    assert [r['source_id'] for r in req['catalog']]==['actual']
    assert [p['card_id'] for p in req['model_request']['inputs']['partition']['primary']]==[req['catalog'][0]['id']]


def test_typed_mapping_feedback_decodes_each_row_before_checking_canonical_sources(tmp_path):
    from lib.scenario_hierarchical_extraction import mapping_feedback
    from lib.scenario_hierarchical_review import build_review_request
    from test_scenario_hierarchical_end_to_end import setup
    _,_,snap,parts,_,_=setup(tmp_path);part=parts['partitions'][0]
    req=build_review_request('extract',{'wire_contract':'source-selection.v2'},{'partition':part},
        {'partition_input_tokens':12000,'partition_output_tokens':2000})
    alias=next(c['card_id'] for c in req['model_request']['inputs']['source_cards'] if c['role']=='user' and c['text'])
    proposal={'atoms':[{'source_cards':[alias],'kind':'constraint','authority':'user_requirement','action':'仅检查草稿',
        'conditions':[],'negation':False,'exceptions':[],'object_hypotheses':[],'time':{'event':None,'effective':None},'local_state':{}}],
        'residuals':[{'source_cards':['s999'],'reason':'non_substantive'}],'assistant_claims':[]}
    feedback=mapping_feedback(snap,part,proposal,['selection_card_invalid'],identity_version='source_semantics.v2',selection_request=req)
    assert feedback['uncovered_primary_ranges']==[]
    assert feedback['item_errors']==[{'field':'residuals','index':0,'errors':['selection_card_invalid']}]
    assert 'atom_source_missing' not in feedback['errors']
