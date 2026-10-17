"""Contract boundaries reproduced independently during the final review."""
from copy import deepcopy
import json
import pytest
from lib.scenario_hierarchical_review import build_review_request,expand_selected_aliases,execute_review,restore_review,_validate,ReviewRejected
from lib.scenario_relation_obligations import validate_relation_proposal
from test_scenario_selection_relations import request,typed
from test_scenario_hierarchical_review import budget


def judgment(req,value):
    return {'result':{**value,'judgment_schema':'attribution-scope-outcome.v1',
        'accepted_scope':'source_attribution_and_intent_only','assistant_reports_are_unverified':True,
        'read_ids':[r['id'] for r in req['catalog']],
        'review_axes':{'attribution':{'status':'sufficient','conditions_preserved':True,'issues':[]},
                     'scope':{'status':'resolved','issues':[]},'outcome':{'status':'not_verified'}}},
        'usage':{'total_tokens':40}}


def test_directed_relation_and_condition_survive_storage_and_readback(tmp_path):
    req=request();raw=typed()
    raw['relations']=[{'kind':'corrects','from':'a0','to':'i0','sources':['p0'],'state':'supported','reason':'speaker corrects earlier report'}]
    raw['record_obligations']=[{'id':'new:condition','kind':'condition','items':['i0'],'sources':[],'state':'open','reason':'condition unresolved'}]
    checked=validate_relation_proposal({'atom_ids':['user-id','assistant-id']},expand_selected_aliases(raw,req),req['inputs']['source_pages'])
    assert checked['errors']==[]
    saved=json.loads(json.dumps(checked['obligations']))
    assert saved[0]['relation_kind']=='corrects' and saved[0]['from_item']=='assistant-id' and saved[0]['to_item']=='user-id'
    assert saved[1]['record_kind']=='condition'
    inputs={**req['inputs'],'obligations':saved}
    follow=build_review_request('readback',req['binding'],inputs,req['limits'])
    projected=follow['model_request']['inputs']['record_obligations']
    assert projected[0]['relation_kind']=='corrects' and projected[0]['from']=='a0' and projected[0]['to']=='i0'
    assert projected[1]['kind']=='condition'
    response=typed();response['record_obligations']=[{'id':'o0','kind':'correction','items':['a0','i0'],'sources':['p0'],'state':'supported','reason':'readback supports correction'}]
    updated=validate_relation_proposal({'atom_ids':['user-id','assistant-id']},expand_selected_aliases(response,follow),inputs['source_pages'])
    assert updated['errors']==[] and updated['obligations'][0]['relation_kind']=='corrects'
    assert updated['obligations'][0]['from_item']=='assistant-id'


@pytest.mark.parametrize('field,value',[('kind','reference'),('items',['i0','a0'])])
def test_existing_directed_obligation_cannot_change_identity(field,value):
    req=request();row={'obligation_id':'old','relation_kind':'corrects','from_item':'assistant-id','to_item':'user-id',
        'atom_ids':['assistant-id','user-id'],'state':'open','reason':'pending','evidence_refs':[]}
    follow=build_review_request('readback',req['binding'],{**req['inputs'],'obligations':[row]},req['limits'])
    response=typed();entry={'id':'o0','kind':'correction','items':['a0','i0'],'sources':['p0'],'state':'supported','reason':'readback'}
    entry[field]=value;response['record_obligations']=[entry]
    with pytest.raises(ValueError):expand_selected_aliases(response,follow)


@pytest.mark.parametrize('same',[False,True])
def test_duplicate_state_target_rejected_before_seal_and_cache_restore(tmp_path,same):
    req=request();raw=typed();raw['states']=[{'item':'i0','state':'unresolved','sources':[]},
        {'item':'i0','state':'unresolved' if same else 'current','sources':[]}]
    response=judgment(req,raw)
    assert _validate(req,response)=='selection_relation_invalid'
    receipt=execute_review(req,lambda _:response,budget(tmp_path),source_current=lambda:True,authorize_request=None)
    assert receipt['status']=='rejected'
    assert restore_review(dict(receipt),req,budget(tmp_path)) is None


@pytest.mark.parametrize('name',['i999','a999','p999','o999','s999','z999','c999','i0','p0','freehand'])
def test_new_obligation_namespace_cannot_hide_unknown_or_wrong_category_alias(name):
    raw=typed();raw['record_obligations']=[{'id':name,'kind':'reference','items':['i0'],'sources':[],'state':'open','reason':'pending'}]
    with pytest.raises(ValueError):expand_selected_aliases(raw,request())


@pytest.mark.parametrize('mutation',['reason','status','response'])
def test_modified_cached_veto_reason_never_dispatches_mapping_repair(tmp_path,mutation):
    from lib.scenario_hierarchical_execution import ReviewExecutor
    from test_scenario_proposal_authority import proposal_request
    req=proposal_request();req['binding']['wire_contract']='source-selection.v2';b=budget(tmp_path);calls=[]
    def provider(_):
        calls.append(1);return {'result':{'accept':False},'usage':{'total_tokens':40}}
    runner=ReviewExecutor(req['binding'],req['limits'],tmp_path,provider,b,lambda:True,None,lambda _:True)
    with pytest.raises(ReviewRejected,match='semantic_rejected'):runner('extract',req['inputs'])
    files=list((tmp_path/'reviews').glob('*.json'));assert len(files)==1
    raw=json.loads(files[0].read_text())
    if mutation=='reason':raw['reason']='selection_schema_invalid'
    elif mutation=='status':raw.update(status='unavailable',reason='provider_failed')
    else:raw['provider_response']['result']['accept']=True
    files[0].write_text(json.dumps(raw))
    with pytest.raises(ValueError,match='review_cache_invalid'):runner('extract',req['inputs'])
    assert len(calls)==1 and b.status()['requests_used']==1


def test_model_relation_instruction_describes_json_objects_not_array_tuples():
    req=request();instruction=req['model_request']['instruction']
    assert '"relations":[{"kind"' in instruction
    assert '"record_obligations":[{"id"' in instruction
    assert '"relation":{' not in instruction and '"record_obligation":{' not in instruction
    assert 'read_ids' in instruction and 'new:' in instruction
