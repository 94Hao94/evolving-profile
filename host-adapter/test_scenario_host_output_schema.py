"""Real envelope constraints exclude source-page IDs from record endpoints."""
from copy import deepcopy
import pytest
from jsonschema import Draft202012Validator
from lib.scenario_coverage_provider import ConfiguredCoverageProvider
from test_scenario_host_planes import request
from lib.scenario_hierarchical_review import build_review_request


def provider():
    return ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture',
        'EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid','EVOLVING_PROFILE_API_LLM_API_KEY':'not-real'})


def merge_request():
    return build_review_request('merge',{'wire_contract':'source-selection.v3'},
       {'atoms':[{'atom_id':'u','authority':'user_requirement'}],
        'assistant_claims':[{'atom_id':'a','authority':'assistant_report'}],
        'source_pages':[{'page_id':'p','role':'user','text':'Different actors.','source_readback':True}]},
       {'partition_input_tokens':12000,'partition_output_tokens':2000})


def validator(req):
    schema=provider().request_envelope(req)['response_format']['json_schema']['schema']
    Draft202012Validator.check_schema(schema)
    return schema


def test_real_v3_envelope_requests_schema_but_v2_remains_json_object():
    req=request();old=deepcopy(req);old['binding']['wire_contract']='source-selection.v2'
    assert provider().request_envelope(req)['response_format']['type']=='json_schema'
    assert provider().request_envelope(old)['response_format']=={'type':'json_object'}
    assert 'fixture.invalid' not in str(validator(req))


def test_schema_record_endpoint_and_state_cannot_select_page_or_obligation():
    schema=validator(merge_request());p=schema['properties']
    relation=Draft202012Validator(p['relations']['items']);state=Draft202012Validator(p['states']['items'])
    good={'kind':'responds_to','from':'a0','to':'i0','sources':['p0'],'state':'supported','reason':'reported reply'}
    assert relation.is_valid(good)
    for bad in ['p0','o0','i999']:
        assert not relation.is_valid({**good,'to':bad})
        assert not state.is_valid({'item':bad,'state':'current','sources':[]})
    assert state.is_valid({'item':'a0','state':'reported','sources':['p0']})


def test_schema_flat_item_source_roles_and_host_fields_remain_disjoint():
    schema=validator(request());item_schema=schema['properties']['proposal']['properties']['items']['items']
    valid={'kind':'request','source_cards':['s0'],'action':'检查','claim':'','conditions':['只草稿'],
        'negation':False,'exceptions':[],'object_hypotheses':[],'time':{'event':None,'effective':None},'local_state':''}
    check=Draft202012Validator(item_schema)
    assert check.is_valid(valid)
    assert check.is_valid({**valid,'kind':'report','source_cards':['s1']})
    for mutation in [{'source_cards':['s0','s1']},{'authority':'user_requirement'},{'source_cards':['p0']},{'kind':'report'}]:
        assert not check.is_valid({**valid,**mutation})


def test_schema_review_never_forces_positive_attribution_or_resolved_scope():
    props=validator(merge_request())['properties']['review_axes']['properties']
    assert Draft202012Validator(props['attribution']).is_valid({'status':'defective','conditions_preserved':False,'issues':['lost negation']})
    assert Draft202012Validator(props['scope']).is_valid({'status':'unresolved','issues':['unknown object']})
    assert Draft202012Validator(props['outcome']).is_valid({'status':'not_verified'})
    assert not Draft202012Validator(props['outcome']).is_valid({'status':'verified'})


@pytest.mark.parametrize('role,sequence,readback,compressed',[
    ('assistant',7,True,True),('user',7,True,False),('assistant',8,True,False),('assistant',7,False,False)])
def test_actual_wire_references_duplicate_literal_only_with_same_read_source(role,sequence,readback,compressed):
    text='历史报告未核验🙂。'*30
    inputs={'assistant_claims':[{'atom_id':'a','authority':'assistant_report','action':'报告','claim':text,'source_order':[7]}],
        'source_pages':[{'page_id':'p','role':role,'sequence':sequence,'text':text,'source_readback':readback}]}
    original=deepcopy(inputs)
    req=build_review_request('merge',{'wire_contract':'source-selection.v3'},inputs,
        {'partition_input_tokens':12000,'partition_output_tokens':2000})
    body=provider().request_envelope(req);data=__import__('json').loads(body['messages'][1]['content'])['inputs']
    row=data['assistant_claims'][0]
    assert req['inputs']==original and data['source_pages'][0]['text']==text
    if compressed:
        assert row['reported_statement_pages']==['p0'] and 'reported_statement' not in row
        assert body['messages'][1]['content'].count(text)==1
    else:assert row['reported_statement']==text and 'reported_statement_pages' not in row


def test_short_report_reference_never_makes_wire_larger():
    req=build_review_request('merge',{'wire_contract':'source-selection.v3'},
        {'assistant_claims':[{'atom_id':'a','authority':'assistant_report','claim':'ok','source_order':[7]}],
         'source_pages':[{'page_id':'p','role':'assistant','sequence':7,'source_readback':True,'text':'ok'}]},
        {'partition_input_tokens':12000,'partition_output_tokens':2000})
    assert req['model_request']['inputs']['assistant_claims'][0]['reported_statement']=='ok'


def test_actual_readback_retains_original_sequence_for_exact_report_reference(tmp_path):
    from test_scenario_hierarchical_end_to_end import setup,controlled
    from test_scenario_review_partial import run
    state,_,snap,parts,settings,b=setup(tmp_path);base=controlled([]);readbacks=[]
    def model(req):
        value=base(req);data=req['model_request']['inputs']
        if req['stage']=='merge':
            target=data['assistant_claims'][0]['atom_id']
            value['result']['record_obligations']=[{'id':'new:report-source','kind':'reference','items':[target],
                'sources':[],'state':'open','reason':'read reported source'}]
        if req['stage']=='readback':
            readbacks.append(req)
            assert data['assistant_claims'][0]['reported_statement_pages']==['p0']
            page=req['inputs']['source_pages'][0];source=next(u for u in snap['units'] if u['unit_id']==page['unit_id'])
            assert page['sequence']==source['sequence']
            o=data['record_obligations'][0]
            value['result']['record_obligations']=[{'id':o['id'],'kind':o['kind'],'items':o['items'],
                'sources':['p0'],'state':'supported','reason':'literal source read'}]
        return value
    result=run(state,snap,parts,settings,b,model)
    assert result['status']=='scope_reviewed' and len(readbacks)==1
