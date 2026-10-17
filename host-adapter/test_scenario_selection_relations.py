from copy import deepcopy
import pytest
from lib.scenario_hierarchical_review import build_review_request,expand_selected_aliases


def request():
    return build_review_request('merge',{'wire_contract':'source-selection.v2'},
      {'task_id':'t','atoms':[{'atom_id':'user-id','authority':'user_requirement','action':'inspect'}],
       'assistant_claims':[{'atom_id':'assistant-id','authority':'assistant_report','claim':'I reported failure.'}],
       'source_pages':[{'page_id':'page-id','text':'Please inspect. I reported failure.','role':'assistant','source_readback':True}]},
      {'partition_input_tokens':12000,'partition_output_tokens':2000})


def typed():
    return {'wire_schema':'source-selection.v2','relations':[],'record_obligations':[],'states':[],
            'discovery_complete':True}


def test_typed_relation_pair_expands_real_page_without_rewriting_response():
    raw=typed();raw['relations']=[{'kind':'responds_to','from':'a0','to':'i0','sources':['p0'],'state':'supported','reason':'reported reply'}]
    before=deepcopy(raw);value=expand_selected_aliases(raw,request())
    row=value['obligations'][0]
    assert row['atom_ids']==['assistant-id','user-id'] and row['relation_kind']=='responds_to'
    assert row['from_item']=='assistant-id' and row['to_item']=='user-id'
    assert row['evidence_refs'][0]['quote']=='Please inspect. I reported failure.'
    assert value['object_links']==[] and raw==before


@pytest.mark.parametrize('change',[
 {'from':'p0'},{'to':'i0','from':'i0'},{'sources':['i0']},{'sources':['unknown']},
 {'atom_id':'i0'},{'kind':'verification'},{'source_refs':[]},
])
def test_bad_relation_role_pair_or_mixed_form_is_rejected(change):
    raw=typed();row={'kind':'same_object','from':'i0','to':'a0','sources':['p0'],'state':'supported','reason':'identity'}
    row.update(change);raw['relations']=[row]
    with pytest.raises(ValueError):expand_selected_aliases(raw,request())


def test_single_record_state_is_not_a_two_record_identity_link():
    raw=typed();raw['states']=[{'item':'a0','state':'reported','sources':['p0']}]
    value=expand_selected_aliases(raw,request())
    assert value['object_links']==[] and value['group_states'][0]['atom_id']=='assistant-id'


def test_model_outcome_exemption_cannot_hide_record_obligations():
    raw=typed();raw['outcome_notes']=[{'items':['i0'],'reason':'identity unknown'}]
    with pytest.raises(ValueError):expand_selected_aliases(raw,request())


def test_input_obligation_uses_same_typed_names_and_request_scoped_ids():
    inputs={'atoms':[{'atom_id':'u','authority':'user_requirement','action':'inspect'}],
       'obligations':[{'obligation_id':'pending','record_kind':'reference','atom_ids':['u'],'state':'open','reason':'referent unknown','evidence_refs':[]}],
       'prior_states':[{'atom_id':'u','state':'unresolved','evidence_refs':[]}]}
    req=build_review_request('readback',{'wire_contract':'source-selection.v2'},inputs,{'partition_input_tokens':12000,'partition_output_tokens':2000})
    data=req['model_request']['inputs']
    assert data['record_obligations'][0]['id']=='o0' and data['record_obligations'][0]['items']==['i0']
    assert data['previous_states'][0]['item']=='i0'
    assert 'obligations' not in data and 'prior_states' not in data
    assert req['inputs']==inputs


@pytest.mark.parametrize('uncertain',[False,True])
def test_host_outcome_note_never_verifies_success_or_erases_record_scope(tmp_path,uncertain):
    from test_scenario_hierarchical_end_to_end import setup,controlled
    from test_scenario_review_partial import run
    from lib.scenario_hierarchical_read import read_hierarchical_view
    from test_scenario_coverage_incremental import job
    state,_,s,parts,settings,budget=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        out=base(req)
        if req['stage']=='extract':
            out['result']['proposal']['items']=[r for r in out['result']['proposal']['items'] if r['kind']!='report']
            out['result']['proposal']['items'].extend([{'source_cards':[c['card_id']],
                'kind':'report','action':'report completion'} for c in req['model_request']['inputs']['source_cards'] if c['role']=='assistant' and c['text']])
        if req['stage']=='leaf' and uncertain:
            out['result']['review_axes']['scope']={'status':'unresolved','issues':['project identity unknown']}
        return out
    result=run(state,s,parts,settings,budget,provider)
    assert len(result['outcome_notes'])==1 and result['outcome_notes'][0]['external_fact_verified'] is False
    assert result['coverage']['target_complete'] is (not uncertain)
    assert result['coverage']['task_outcome']=='not_verified'
    view=read_hierarchical_view(state,job()['session_id'],'relations',cursor=None,permission=s['permission'],expected_scope=s['scope'],requirement_id=None)
    assert view['outcome_notes'][0]['kind']=='assistant_report_unverified'
