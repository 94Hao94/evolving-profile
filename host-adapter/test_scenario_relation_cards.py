from copy import deepcopy
import pytest
from lib.scenario_hierarchical_review import build_review_request,expand_selected_aliases
from lib.scenario_relation_obligations import validate_relation_proposal


def request():
    return build_review_request('merge',{}, {'atoms':[{'atom_id':'a'},{'atom_id':'b'}],
      'source_pages':[{'page_id':'p','text':'项目乙沿用方案甲的流程，但金额分别核对。','role':'user','source_readback':True}]},
      {'partition_input_tokens':12000,'partition_output_tokens':2000})


def test_entire_page_choice_is_bound_to_this_request_and_preserves_raw_response():
    req=request();raw={'obligations':[],'object_links':[{'atom_ids':['r0','r1'],
      'source_refs':[{'page_id':'r2','source_selection':'entire_page'}]}]};original=deepcopy(raw)
    result=expand_selected_aliases(raw,req)
    checked=validate_relation_proposal({'atom_ids':['a','b']},result,req['inputs']['source_pages'])
    assert checked['errors']==[] and len(checked['object_links'])==1
    ref=checked['object_links'][0]['source_refs'][0]
    assert ref['quote']=='项目乙沿用方案甲的流程，但金额分别核对。'
    assert ref['page_id']=='p' and ref['offset_binding']=='host_selected_entire_page'
    assert raw==original


@pytest.mark.parametrize('ref',[
 {'page_id':'unknown','source_selection':'entire_page'},
 {'page_id':'r0','source_selection':'entire_page'},
 {'page_id':'r2','source_selection':'entire_page','quote':'篡改的引文'},
 {'page_id':'r2','source_selection':'all_history'},
])
def test_unknown_mixed_or_wrong_kind_page_selector_never_gains_evidence(ref):
    with pytest.raises(ValueError,match='^relation_source_selector_invalid$'):
        expand_selected_aliases({'evidence_refs':[ref]},request())


def test_unread_page_selector_cannot_be_promoted_to_original_readback():
    req=request();req['inputs']['source_pages'][0]['source_readback']=False
    with pytest.raises(ValueError,match='^relation_source_selector_invalid$'):
        expand_selected_aliases({'evidence_refs':[{'page_id':'r2','source_selection':'entire_page'}]},req)


@pytest.mark.parametrize('identity',['unknown',[]])
def test_bad_selector_is_rejected_before_receipt_can_be_sealed_as_reviewed(tmp_path,identity):
    from lib.scenario_hierarchical_review import execute_review
    from test_scenario_hierarchical_review import budget,accepted
    req=request()
    def provider(payload):
        value=accepted(payload)
        value['result'].update(discovery_complete=True,obligations=[],object_links=[{'atom_ids':['r0','r1'],
           'source_refs':[{'page_id':identity,'source_selection':'entire_page'}]}])
        return value
    receipt=execute_review(req,provider,budget(tmp_path),source_current=lambda:True,authorize_request=None)
    assert receipt['status']=='rejected' and receipt['reason']=='relation_source_selector_invalid'


def test_merge_stage_really_receives_materialized_originals(tmp_path):
    from test_scenario_hierarchical_end_to_end import setup,controlled,job
    from lib.scenario_hierarchical_incremental import process_hierarchical_stages,authorize_evaluation
    state,store,s,parts,settings,budget=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        result=base(req)
        if req['stage']=='merge':
            pages=req['inputs'].get('source_pages',[])
            assert pages and pages[0]['source_readback'] is True
            assert pages[0]['text']=='仅检查草稿。' and pages[0]['raw_line_sha256']
        return result
    r=process_hierarchical_stages(job(),s,parts,settings,root=state,provider=provider,budget=budget,
       permission_getter=lambda:job()['permission'],scope_getter=lambda:s['scope'],authorize_request=None,
       parent_lease_valid=None,evaluation_authorization=authorize_evaluation(s,budget,'source-card-fixture'))
    assert r['status']=='scope_reviewed' and r['raw_review_pages']>=1


@pytest.mark.parametrize('identity',['unknown',[]])
def test_bad_selection_returns_stable_partial_and_cached_rejection_never_replays(tmp_path,identity):
    from test_scenario_hierarchical_end_to_end import setup,controlled
    from test_scenario_review_partial import run
    state,_,s,parts,settings,budget=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        value=base(req)
        if req['stage']=='merge':
            atom=req['model_request']['inputs']['atoms'][0]['atom_id']
            value['result']['object_links']=[{'atom_ids':[atom,atom],
              'source_refs':[{'page_id':identity,'source_selection':'entire_page'}]}]
        return value
    for _ in range(2):
        r=run(state,s,parts,settings,budget,provider)
        assert r['coverage']['target_complete'] is False
        assert r['status']=='unavailable'
    assert len(calls)==3 and budget.status()['requests_used']==3
