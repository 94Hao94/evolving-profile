from test_scenario_hierarchical_end_to_end import setup,controlled
from test_scenario_review_axes import typed
from test_scenario_coverage_incremental import job
from lib.scenario_hierarchical_incremental import process_hierarchical_stages,authorize_evaluation
from lib.scenario_hierarchical_store import HierarchicalStore
from lib.scenario_coverage_partition import partition_snapshot
from lib.scenario_hierarchical_read import read_hierarchical_view


def run(state,s,parts,settings,budget,provider):
    return process_hierarchical_stages(job(),s,parts,settings,root=state,provider=provider,budget=budget,
        permission_getter=lambda:s['permission'],scope_getter=lambda:s['scope'],authorize_request=None,parent_lease_valid=None,
        evaluation_authorization=authorize_evaluation(s,budget,'axes-fixture'))


def axes_provider(calls,scope='unresolved'):
    base=controlled(calls)
    def provider(request):
        original=base(request);v=typed(request,scope=scope if request['stage']=='leaf' else 'resolved')
        if request['stage']=='extract':v['result']['proposal']=original['result']['proposal']
        if request['model_request'].get('wire_contract'):v['result']['wire_schema']=request['model_request']['wire_contract']
        if request['stage'] in {'merge','readback'}:
            if request['model_request'].get('wire_contract'):v['result'].update(discovery_complete=True,relations=[],record_obligations=[],states=[])
            else:v['result'].update(discovery_complete=True,obligations=[],object_links=[])
        return v
    return provider


def test_unresolved_scope_retains_reviewed_attribution_without_global_green(tmp_path):
    state,store,s,parts,settings,budget=setup(tmp_path);calls=[]
    result=run(state,s,parts,settings,budget,axes_provider(calls))
    assert result['atom_count']>0 and result['coverage']['leaf_count']==1
    assert result['coverage']['attribution_review']=='complete'
    assert result['coverage']['scope_review']=='unresolved'
    assert result['coverage']['target_complete'] is False and result['coverage']['unresolved_count']>0
    assert result['coverage']['task_outcome']=='not_verified'
    assert all(g['status']!='scope_reviewed' for g in result['coverage']['groups'].values())
    view=read_hierarchical_view(state,job()['session_id'],'requirements',cursor=None,permission=s['permission'],expected_scope=s['scope'],requirement_id=None)
    assert view['requirements'][0]['semantic_review_status']=='reviewed'
    assert view['requirements'][0]['scope_review_status']=='unresolved'


def test_no_context_preserves_literal_but_never_resolves_identity_or_repeats_model(tmp_path):
    state,store,s,parts,settings,budget=setup(tmp_path);calls=[]
    r=run(state,s,parts,settings,budget,axes_provider(calls,scope='needs_context'))
    assert r['atom_count']>0 and r['coverage']['scope_review']=='unresolved'
    assert len([c for c in calls if c['stage']=='leaf'])==1
    assert r['context_recovery'][0]['stop_reason']=='context_unavailable'
    assert r['source_readback'] is False and r['coverage']['target_complete'] is False


def test_semantic_failure_does_not_abort_other_independent_leaves(tmp_path):
    state,store,s,_,settings,budget=setup(tmp_path);parts=partition_snapshot(s,capacity=12);calls=[];base=controlled(calls)
    def provider(request):
        value=base(request)
        if request['stage']=='leaf' and len([c for c in calls if c['stage']=='leaf'])==1:value['result']['accept']=False
        return value
    r=run(state,s,parts,settings,budget,provider)
    assert len([c for c in calls if c['stage']=='extract'])>=2
    assert r['coverage']['leaf_count']>0 and r['coverage']['target_complete'] is False
    graph=HierarchicalStore(state/'hierarchical/graphs.sqlite3',readonly=True).load_current(s['scope'],s['permission'])['graph']
    assert graph['candidate_atoms'] and graph['leaf_failures']
    assert len(graph['manifest']['leaf_partition_ids'])==2
    assert set(graph['manifest']['target_source_unit_ids'])=={u['unit_id'] for u in s['units'] if u['selection']=='visible_message'}
