import pytest
from lib import scenario_raw_readback as raw
from test_scenario_hierarchical_end_to_end import setup


def test_hierarchical_source_pages_reconstruct_exact_text(tmp_path):
    assert hasattr(raw,'read_materialized_page')
    state,store,s,_,_,_=setup(tmp_path)
    unit=next(u for u in s['units'] if u['role']=='user');text=[];offset=0
    while True:
        page=raw.read_materialized_page(s,unit_id=unit['unit_id'],text_offset=offset,max_chars=3,
            permission=s['permission'],coverage_root=state)
        assert page['source_readback'] is True
        text.append(page['text'])
        if page['next_offset'] is None:break
        offset=page['next_offset']
    assert ''.join(text)==unit['text']


def test_source_page_rejects_permission_stale_source_and_invalid_offsets(tmp_path):
    assert hasattr(raw,'read_materialized_page')
    state,store,s,_,_,_=setup(tmp_path);unit=next(u for u in s['units'] if u['role']=='user')
    def read(**kw):return raw.read_materialized_page(s,unit_id=unit['unit_id'],text_offset=0,max_chars=10,
        permission=kw.pop('permission',s['permission']),coverage_root=state,**kw)
    with pytest.raises(ValueError):read(permission={'allowed':False})
    with open(s['location']['path'],'a') as f:f.write('{}\n')
    with pytest.raises(ValueError):read()


def test_four_view_projection_has_bound_cursor_and_real_original_body(tmp_path):
    import copy
    from lib.scenario_coverage_read import read_coverage_view
    from lib.scenario_hierarchical_incremental import process_hierarchical_stages,authorize_evaluation
    from test_scenario_hierarchical_end_to_end import controlled
    from test_scenario_coverage_incremental import job
    state,store,s,parts,settings,budget=setup(tmp_path)
    result=process_hierarchical_stages(job(),s,parts,settings,root=state,provider=controlled([]),budget=budget,
        permission_getter=lambda:s['permission'],scope_getter=lambda:s['scope'],authorize_request=None,parent_lease_valid=None,
        evaluation_authorization=authorize_evaluation(s,budget,'fixture'))
    def read(view,**kw):return read_coverage_view(state,job()['session_id'],view,permission=s['permission'],
        review_protocol='hierarchical_review.v1',**kw)
    overview=read('overview')
    assert overview['coverage_contract']=='hierarchical_review.v1'
    assert overview['coverage']['cross_scope_exhaustiveness']=='not_exhaustive'
    rows=read('requirements')['requirements']
    assert rows[0]['text']=='仅检查草稿。'
    page=read('source',requirement_id=rows[0]['requirement_id'])
    assert page['raw_source']['text']=='仅检查草稿。'
    assert page['source_readback'] is True
    assert read('relations')['relations_total']==0
