"""Switching protocols preserves raw navigation, not another protocol's verdict."""
import json
import pytest
from lib.scenario_coverage_read import read_coverage_view
from lib.scenario_coverage_incremental import process_coverage_job
from test_scenario_coverage_incremental import job
from test_scenario_source_codec import SID,source


def foreign_receipt(tmp_path):
    root,_,_=source(tmp_path,text='先核对原文，不要发布。');state=tmp_path/'state'
    result=process_coverage_job(job(),root,{},store_root=state)
    status=state/'status'/f'{SID}.json'
    foreign={**json.loads(status.read_text()),'review_protocol':'hierarchical_review.v1','coverage_contract':'hierarchical_review.v1',
        'status':'scope_reviewed','semantic_review_status':'automated_declared_scope_accepted','published':True,'model_calls':9,
        'review_binding':{'protocol':'hierarchical_review.v1'},'coverage':{'status':'accepted','target_complete':True},
        'current_conditions':[{'intent_id':'foreign-only','source_quote':'错误的跨协议现行结论'}]}
    status.write_text(json.dumps(foreign))
    nav=state/'navigation'/f'{SID}.json';nav.parent.mkdir(parents=True,exist_ok=True)
    inventory=json.loads((state/'inventories'/(result['snapshot_id']+'.json')).read_text())
    rid=inventory['requirements']['requirements'][0]['requirement_id']
    nav.write_text(json.dumps({'snapshot_id':result['snapshot_id'],'generation':result['generation'],
        'review_binding':foreign['review_binding'],'coverage':{'status':'accepted','relations':[{'type':'supersedes','from':'foreign','to':'other'}]},
        'intent_ledger':[{'requirement_id':rid,'intent_id':'foreign-only','kind':'constraint','source_quote':'错误结论','source_locator':{},'status':'covered'}]}))
    return state


def test_legacy_overview_never_inherits_a_hierarchical_semantic_pass(tmp_path):
    state=foreign_receipt(tmp_path);before=(state/'status'/f'{SID}.json').read_bytes()
    page=read_coverage_view(state,SID,'overview',permission=job()['permission'])
    assert page['review_protocol']=='segment_coverage.v1'
    assert page['coverage_contract']=='segment_coverage.v1'
    assert page['status']=='global_pending' and page['semantic_review_status']=='not_reviewed'
    assert page['receipt_review_protocol']=='hierarchical_review.v1'
    assert page['model_calls'] is None and page['published'] is False
    assert not page.get('coverage') and not page.get('current_conditions')
    assert (state/'status'/f'{SID}.json').read_bytes()==before


def test_foreign_protocol_keeps_requirements_and_exact_original_readback(tmp_path):
    state=foreign_receipt(tmp_path)
    page=read_coverage_view(state,SID,'requirements',permission=job()['permission'])
    assert page['requirements'] and all(r['intents']==[] for r in page['requirements'])
    rid=page['requirements'][0]['requirement_id']
    original=read_coverage_view(state,SID,'source',permission=job()['permission'],requirement_id=rid)
    assert original['source_readback'] is True and original['raw_source']['text']=='[role: user; turn: t1; at: None]\n先核对原文，不要发布。'
    relations=read_coverage_view(state,SID,'relations',permission=job()['permission'])
    assert relations['relations']==[] and relations['relations_coverage']=='not_reviewed'


def test_foreign_receipt_does_not_relax_source_permission_checks(tmp_path):
    state=foreign_receipt(tmp_path)
    with pytest.raises(ValueError,match='stale_source_or_permission'):
        read_coverage_view(state,SID,'overview',permission={'allowed':False,'version':'p1'})


def test_untagged_legacy_receipts_stay_compatible_and_get_explicit_protocol(tmp_path):
    root,_,_=source(tmp_path);state=tmp_path/'state';result=process_coverage_job(job(),root,{},store_root=state)
    page=read_coverage_view(state,SID,'overview',permission=job()['permission'])
    assert page['review_protocol']=='segment_coverage.v1'
    assert page['coverage_contract']=='segment_coverage.v1'
    assert page['status']==result['status'] and page['model_calls']==0
    assert page.get('receipt_review_protocol') is None
