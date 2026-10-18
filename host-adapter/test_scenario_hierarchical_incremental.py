import copy
from lib import scenario_hierarchical_incremental as mod


def test_late_clarification_invalidates_remote_dependents():
    assert hasattr(mod,'compute_invalidation')
    previous={'atoms':[{'atom_id':'old_condition','stable_id':'old','source_refs':[{'unit_id':'u1'}]},
                       {'atom_id':'independent_group','stable_id':'independent','source_refs':[{'unit_id':'u2'}]}]}
    current={'atoms':[{'atom_id':'new_condition','stable_id':'new','source_refs':[{'unit_id':'u1'}]},
                      {'atom_id':'independent_group','stable_id':'independent','source_refs':[{'unit_id':'u2'}]}],
             'affected_ids':['old_condition'],'closure_verified':True}
    delta=mod.compute_invalidation(previous,current,{'old_condition':['dependent_parent']})
    assert {'old_condition','dependent_parent'}<=set(delta['stale_ids'])
    assert 'independent_group' not in delta['stale_ids']


def test_unknown_late_referent_conservatively_invalidates_selected_scope():
    assert hasattr(mod,'compute_invalidation')
    previous={'atoms':[{'atom_id':'a','stable_id':'a'},{'atom_id':'b','stable_id':'b'}]}
    current={'atoms':[{'atom_id':'c','stable_id':'c'}],'closure_verified':False}
    delta=mod.compute_invalidation(previous,current,{'a':['parent']})
    assert {'a','b','parent'}<=set(delta['stale_ids'])
    assert delta['expanded_scope']=='selected_target_scope'


def test_append_reuses_exact_leaf_proof_not_a_fabricated_new_http_call(tmp_path):
    import json
    from test_scenario_hierarchical_end_to_end import setup,controlled
    from test_scenario_coverage_incremental import job
    from lib.scenario_coverage_incremental import process_coverage_job
    from lib.scenario_coverage_partition import partition_snapshot
    from lib.scenario_coverage_store import CoverageStore
    state,store,s,parts,settings,budget=setup(tmp_path);calls=[]
    def run(s,parts):
        return mod.process_hierarchical_stages(job(),s,parts,settings,root=state,provider=controlled(calls),budget=budget,
            permission_getter=lambda:job()['permission'],scope_getter=lambda:s['scope'],authorize_request=None,parent_lease_valid=None,
            evaluation_authorization=mod.authorize_evaluation(s,budget,'frozen-fixture-plan'))
    first=run(s,partition_snapshot(s,capacity=40));n=len(calls)
    assert first['status']=='scope_reviewed'
    with open(s['location']['path'],'a') as f:f.write(json.dumps({'type':'response_item','payload':{'type':'message','role':'user',
        'content':[{'type':'input_text','text':'新要求，单独检查。'}]}})+'\n')
    process_coverage_job(job(),tmp_path/'sessions',{},store_root=state)
    import json as j
    current=store.read(j.loads((state/'status'/f"{job()['session_id']}.json").read_text())['snapshot_id'])
    second=run(current,partition_snapshot(current,capacity=40))
    assert second['status']=='scope_reviewed'
    assert second['reused_review_requests']>=4
    assert len(calls)-n<2*second['coverage']['leaf_count']+second['coverage']['discovery_count']
