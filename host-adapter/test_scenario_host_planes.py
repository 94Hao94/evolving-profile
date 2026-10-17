"""Host ownership of actor/record plane, independent of model classifications."""
from copy import deepcopy
import pytest
from lib.scenario_hierarchical_review import build_review_request,expand_selected_aliases,execute_review,restore_review
from test_scenario_hierarchical_review import budget


def request(stage='extract'):
    return build_review_request(stage,{'wire_contract':'source-selection.v3','snapshot_id':'s'},
        {'partition':{'primary':[{'span_id':'u','role':'user','sequence':1,'text':'现在只检查草稿，不要发布。🙂'},
                                {'span_id':'a','role':'assistant','sequence':2,'text':'用户要求发布；我说已经发布，但未核验。'},
                                {'span_id':'empty','role':'user','sequence':3,'text':''}]}},
        {'partition_input_tokens':12000,'partition_output_tokens':2000})


def item(card,kind='request',action='检查草稿'):
    return {'source_cards':[card],'kind':kind,'action':action,'conditions':['当前','仅草稿'],
            'negation':False,'exceptions':[],'object_hypotheses':[],
            'time':{'event':None,'effective':None},'local_state':'expressed'}


def test_host_routes_assistant_quotation_to_report_even_when_kind_is_request():
    req=request();raw={'items':[item('s0'),item('s1',action='用户要求发布')]};saved=deepcopy(raw)
    out=expand_selected_aliases(raw,req)
    assert len(out['atoms'])==1 and len(out['assistant_claims'])==1
    assert out['atoms'][0]['authority']=='user_requirement'
    assert out['assistant_claims'][0]['authority']=='assistant_report'
    assert out['assistant_claims'][0]['source_refs']==[{'span_id':'a','source_selection':'entire_span'}]
    assert raw==saved and req['inputs']['partition']['primary'][2]['text']==''


@pytest.mark.parametrize('kind,field,authority',[
    ('claim','atoms','user_claim'),('correction','atoms','user_requirement'),
    ('non_substantive','residuals',None),('unclassified','residuals',None)])
def test_user_semantic_kind_does_not_choose_source_role(kind,field,authority):
    out=expand_selected_aliases({'items':[item('s0',kind)]},request())
    assert len(out[field])==1 and out['assistant_claims']==[]
    if authority:assert out[field][0]['authority']==authority
    else:assert out[field][0]['reason']==kind


@pytest.mark.parametrize('kind',['claim','correction','non_substantive','unclassified','suggestion'])
def test_no_assistant_semantic_kind_can_create_user_atom_or_residual(kind):
    out=expand_selected_aliases({'items':[item('s1',kind)]},request())
    assert out['atoms']==[] and out['residuals']==[]
    assert out['assistant_claims'][0]['authority']==('assistant_suggestion' if kind=='suggestion' else 'assistant_report')


@pytest.mark.parametrize('field,value',[
    ('authority','user_requirement'),('role','user'),('plane','atoms'),('atom_id','forged'),('source_refs',[])])
def test_model_cannot_override_host_owned_fields(field,value):
    row=item('s1');row[field]=value
    with pytest.raises(ValueError,match='selection_fields_invalid'):expand_selected_aliases({'items':[row]},request())


@pytest.mark.parametrize('cards',[['s0','s1'],['s1','s0'],['s0','s0'],['s2'],['p0'],['unknown'],[]])
def test_invalid_or_mixed_role_source_never_gets_reconstructed_authority(cards):
    row=item('s0');row['source_cards']=cards
    with pytest.raises(ValueError):expand_selected_aliases({'items':[row]},request())


def test_shared_source_distinct_intents_are_not_forced_into_one_record():
    raw={'items':[item('s0',action='检查草稿'),item('s0','constraint','不要发布')]}
    raw['items'][1]['negation']=True
    out=expand_selected_aliases(raw,request())
    assert len(out['atoms'])==2 and out['atoms'][1]['negation'] is True
    assert out['atoms'][0]['source_refs']==out['atoms'][1]['source_refs']


def test_v3_proposal_is_never_silently_reinterpreted_as_v2_containers():
    with pytest.raises(ValueError,match='proposal_fields'):
        expand_selected_aliases({'atoms':[],'residuals':[],'assistant_claims':[]},request())
    with pytest.raises(ValueError,match='proposal_fields'):
        expand_selected_aliases({'items':[],'atoms':[]},request())


def test_v2_still_uses_original_explicit_authority_and_containers():
    req=build_review_request('extract',{'wire_contract':'source-selection.v2'},
        {'partition':{'primary':[{'span_id':'u','role':'user','text':'保留'}]}},
        {'partition_input_tokens':12000,'partition_output_tokens':2000})
    row=item('s0');row['authority']='user_requirement'
    out=expand_selected_aliases({'atoms':[row],'residuals':[],'assistant_claims':[]},req)
    assert out['atoms'][0]['authority']=='user_requirement'
    with pytest.raises(ValueError):expand_selected_aliases({'items':[item('s0')]},req)


def test_actual_receipt_and_cached_restore_keep_raw_flat_response(tmp_path):
    req=request();b=budget(tmp_path);raw={'result':{'wire_schema':'source-selection.v3',
        'proposal':{'items':[item('s0'),item('s1')]},'context_requests':[]},'usage':{'total_tokens':40}}
    before=deepcopy(raw);receipt=execute_review(req,lambda _:raw,b,source_current=lambda:True,authorize_request=None)
    assert receipt['status']=='proposed' and receipt['result']==before['result'] and raw==before
    assert restore_review(dict(receipt),req,b)['result']==before['result']
    wrong=deepcopy(req);wrong['binding']['wire_contract']='source-selection.v2'
    assert restore_review(dict(receipt),wrong,b) is None


def test_explicit_semantic_veto_cannot_become_v3_format_retry(tmp_path):
    r=execute_review(request(),lambda _:{'result':{'accept':False},'usage':{'total_tokens':20}},
        budget(tmp_path),source_current=lambda:True,authorize_request=None)
    assert r['status']=='rejected' and r['reason']=='semantic_rejected'


def test_flat_feedback_reports_only_invalid_item_not_missing_old_fields(tmp_path):
    from test_scenario_hierarchical_end_to_end import setup
    from lib.scenario_hierarchical_extraction import mapping_feedback
    _,_,snap,parts,_,_=setup(tmp_path);part=parts['partitions'][0]
    req=build_review_request('extract',{'wire_contract':'source-selection.v3'},{'partition':part},
        {'partition_input_tokens':12000,'partition_output_tokens':2000})
    raw={'items':[item('s0'),item('unknown'),item('s1','report')]}
    feedback=mapping_feedback(snap,part,raw,['selection_card_invalid'],identity_version='source_semantics.v2',selection_request=req)
    assert feedback['uncovered_primary_ranges']==[]
    assert feedback['item_errors']==[{'field':'items','index':1,'errors':['selection_card_invalid']}]
    assert 'atom_source_missing' not in feedback['errors']


def test_actual_hierarchical_binding_and_rebind_keep_v3_separate(tmp_path):
    from test_scenario_hierarchical_end_to_end import setup
    from lib.scenario_hierarchical_capacity import review_binding
    _,_,snap,_,_,_=setup(tmp_path)
    assert review_binding(snap,None)['wire_contract']=='source-selection.v3'


def test_flat_producer_runs_through_independent_leaf_storage_and_cache(tmp_path):
    from test_scenario_hierarchical_end_to_end import setup,controlled
    from test_scenario_review_partial import run
    from lib.scenario_hierarchical_read import read_hierarchical_view
    from test_scenario_coverage_incremental import job
    state,_,snap,parts,settings,b=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        assert req['binding']['wire_contract']=='source-selection.v3'
        value=base(req)
        if req['stage']=='extract':
            value['result']={'wire_schema':'source-selection.v3','proposal':{'items':[
                item(c['card_id'],action='仅检查草稿' if c['role']=='user' else '助手自报收到')
                for c in req['model_request']['inputs']['source_cards']]},'context_requests':[]}
        return value
    first=run(state,snap,parts,settings,b,provider)
    assert first['status']=='scope_reviewed' and first['model_calls']==3
    assert first['atom_count']==1 and first['assistant_claim_count']==1
    view=read_hierarchical_view(state,job()['session_id'],'requirements',cursor=None,permission=snap['permission'],expected_scope=snap['scope'],requirement_id=None)
    assert view['status']!='unavailable'
    again=run(state,snap,parts,settings,b,provider)
    assert again['status']=='scope_reviewed' and again['model_calls']==0 and b.status()['requests_used']==3


def test_missing_assistant_source_cannot_silently_complete_v3_graph(tmp_path):
    from test_scenario_hierarchical_end_to_end import setup,controlled
    from test_scenario_review_partial import run
    state,_,snap,parts,settings,b=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        value=base(req)
        if req['stage']=='extract':
            value['result']['proposal']={'items':[item(c['card_id']) for c in req['model_request']['inputs']['source_cards'] if c['role']=='user']}
        return value
    result=run(state,snap,parts,settings,b,provider)
    assert result['status']=='intent_gap' and result['coverage']['target_complete'] is False
    assert [r['stage'] for r in calls]==['extract','extract']
    assert 'assistant_character_gap' in calls[1]['inputs']['validation_feedback']['errors']
    assert calls[1]['inputs']['validation_feedback']['uncovered_primary_ranges']


def test_leaf_seal_cannot_rescue_missing_assistant_coverage(tmp_path):
    from test_scenario_hierarchical_end_to_end import setup
    from test_scenario_review_axes import typed
    from lib.scenario_intent_atoms import bind_leaf_review
    _,_,snap,parts,_,b=setup(tmp_path);part=parts['partitions'][0]
    req=build_review_request('extract',{'wire_contract':'source-selection.v3','snapshot_id':snap['snapshot_id']},
        {'partition':part},{'partition_input_tokens':12000,'partition_output_tokens':2000})
    user=next(c for c in req['model_request']['inputs']['source_cards'] if c['role']=='user')
    proposal=expand_selected_aliases({'items':[item(user['card_id'])]},req)
    leaf=build_review_request('leaf',req['binding'],{'partition':part,'proposal':proposal},req['limits'])
    receipt=execute_review(leaf,typed,b,source_current=lambda:True,authorize_request=None)
    assert receipt['status']=='reviewed'
    bound=bind_leaf_review(snap,part,proposal,receipt)
    assert bound['semantic_review_status']=='not_reviewed' and bound['errors']==['assistant_character_gap']
