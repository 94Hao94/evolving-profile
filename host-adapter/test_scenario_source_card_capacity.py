from lib.scenario_coverage_contract import validate_settings
from lib.scenario_coverage_partition import partition_snapshot,validate_partition
from lib.scenario_coverage_store import CoverageStore
from lib.scenario_coverage_incremental import process_coverage_job
from test_scenario_hierarchical_end_to_end import controlled
from test_scenario_source_codec import source
from test_scenario_coverage_incremental import job
from test_scenario_hierarchical_review import budget
from test_scenario_review_partial import run


def test_leaf_input_capacity_splits_locally_without_paying_for_oversized_dispatch(tmp_path):
    root,_,_=source(tmp_path,text='Do not publish; only inspect. 🙂 '*60);state=tmp_path/'state'
    structural=process_coverage_job(job(),root,{},store_root=state)
    s=CoverageStore(state/'coverage.sqlite3').read(structural['snapshot_id']);parts=partition_snapshot(s,capacity=2000)
    settings=validate_settings({'mode':'assisted','model_trial':True,'review_protocol':'hierarchical_review.v1'})
    settings['limits']['partition_input_tokens']=6000;b=budget(tmp_path,requests=40);calls=[];base=controlled(calls)
    def provider(req):
        from lib.scenario_coverage_contract import canonical
        assert len(canonical(req['model_request']))<=6000
        r=base(req)
        if req['stage']=='extract':
            for atom in r['result']['proposal']['items']:
                    ids=atom['source_cards']
                    atom['action']=''.join(c['text'] for c in req['model_request']['inputs']['source_cards'] if c['card_id'] in ids)*2
        return r
    result=run(state,s,parts,settings,b,provider)
    # This intentionally verbose producer stresses leaf input. Later merge
    # capacity is independent; it must not be confused with unread leaf text.
    assert result['coverage']['intent_review']=='complete'
    assert any(r['stage']=='leaf' for r in calls)
    assert any(r.get('failure_kind')=='input_wire_capacity' for r in result['output_recovery'])
    assert all(r.get('failed_reservation_id') is None for r in result['output_recovery'])
    from lib.scenario_hierarchical_store import HierarchicalStore
    graph=HierarchicalStore(state/'hierarchical/graphs.sqlite3',readonly=True).load_current(s['scope'],s['permission'])['graph']
    assert validate_partition(graph['effective_partitions'],s)['complete']
    assert b.status()['requests_used']==len(calls)


def test_merge_page_measurement_includes_actual_inherited_states_without_losing_proof():
    from lib.scenario_evidence_capsule import build_capsules
    from lib.scenario_hierarchical_transport import merge_pages,fits_request
    from lib.scenario_hierarchical_review import build_review_request
    rows=[{'atom_id':str(i),'source_quote':'原句','action':'a'*150,'authority':'user_requirement'} for i in range(3)]
    capsule=build_capsules({},rows,[],[],{'partition_input_tokens':6000})
    states=[{'atom_id':'older','state':'unresolved','evidence_refs':[{'page_id':'old','quote':'q'*2000}]}]
    def sources(ids):return [{'page_id':'p'+i,'text':'x'*2000,'role':'user','source_readback':True} for i in ids]
    limits={'partition_input_tokens':6000,'partition_output_tokens':2000}
    pages=merge_pages({}, {'node_id':'n'},['0','1','2'],capsule,[],limits,lambda r:None,source_reader=sources,prior_states=states)
    assert sorted(x['atom_id'] for p in pages for x in p['atoms'])==['0','1','2']
    for page in pages:
        assert page['prior_states']==states
        req=build_review_request('merge',{},page,limits)
        assert fits_request(req,lambda r:None)
        prior=req['model_request']['inputs']['prior_states'][0]
        assert prior['state']=='unresolved' and prior['evidence_ref_count']==1 and prior['evidence_set_sha256']
        assert 'evidence_refs' not in prior
