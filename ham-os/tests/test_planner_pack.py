from ham.planner import need_graph
from ham.coverage import receipt
from ham.packs import build_pack

def test_needgraph_routes_handoff_and_provenance():
 g=need_graph('继续那个任务，给我原文证据'); assert {'task_capsule','provenance'}<=set(g['facets']); assert g['stages'][-1]=='stage_c'
def test_coverage_never_calls_partial_complete(): assert receipt(['a','b'],['a'])['coverage_status']=='incomplete'
def test_pack_obeys_dynamic_budget_and_keeps_expansion():
 p=build_pack([{'text':'a','tokens':3},{'text':'b','tokens':3}],3); assert len(p['items'])==1 and p['expansion_handle']
def test_needgraph_paraphrases_keep_handoff_semantics():
    for q in ('继续此前的工作','接管上一个任务','继续这个任务'):
        assert 'task_capsule' in need_graph(q)['facets']
def test_fault_isolation_exposes_missing_facet_without_false_success():
    r=receipt(['task_capsule','provenance'],['task_capsule']); assert r['coverage_status']=='incomplete' and r['missing_dimensions']==['provenance']
