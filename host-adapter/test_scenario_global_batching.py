"""All-pairs review must not pay for identical requirements in separate calls."""
from lib.scenario_global_review import plan_global_review, global_payload


def make_ledger(n=4):
    rows=[{'requirement_id':str(i),'text':'原始条件🙂'+str(i),'role':'user','sequence':i,
           'snapshot_id':'s','partition_ids':[str(i)],'assistant_context':[]} for i in range(n)]
    return {'requirements':{'requirements':rows},'local_reviews':[], 'partition_plan':{'partitions':[]}}


def test_shared_context_batches_all_edges_without_top_k_omissions():
    ledger=make_ledger(8)
    plan=plan_global_review({'snapshot_id':'s','generation':1},ledger,capacity=6000)
    assert len(plan['parts']) < 36
    assert len(plan['required_edges']) == 28
    assert {rid for p in plan['parts'] for rid in p['requirement_ids']} == set(map(str,range(8)))
    assert {eid for p in plan['parts'] for eid in p['edge_ids']} == {e['edge_id'] for e in plan['required_edges']}
    payload=global_payload(plan['parts'][0], {r['requirement_id']:r for r in ledger['requirements']['requirements']}.__getitem__,plan=plan)
    assert 1 <= len(payload['requirements']) <= 8
    assert payload['response_schema']['required']==['accept','read_requirement_ids','reviewed_edge_ids','requirement_states','relations','issues']
    assert payload['response_schema']['properties']['reviewed_edge_ids']['items']['enum']==plan['parts'][0]['edge_ids']


def test_capacity_split_keeps_each_required_pair_and_each_requirement():
    ledger=make_ledger(5)
    plan=plan_global_review({'snapshot_id':'s','generation':1},ledger,capacity=44)
    assert 1 < len(plan['parts']) < 15
    byid={r['requirement_id']:r for r in ledger['requirements']['requirements']}
    edges={e['edge_id']:e for e in plan['required_edges']}
    assert {rid for p in plan['parts'] for rid in p['requirement_ids']} == set(byid)
    assert {eid for p in plan['parts'] for eid in p['edge_ids']} == set(edges)
    for part in plan['parts']:
        assert part['source_input_bytes'] <= 44
        for eid in part['edge_ids']:
            assert {edges[eid]['from'],edges[eid]['to']} <= set(part['requirement_ids'])


def test_oversized_requirement_stays_partial_and_no_edge_is_dropped():
    ledger=make_ledger(3);ledger['requirements']['requirements'][1]['text']='不可删减的长条件'*300
    plan=plan_global_review({'snapshot_id':'s','generation':1},ledger,capacity=80)
    assert plan['plan_complete'] is False
    assert plan['reason'] == 'global_source_partition_capacity_exceeded'
    assert len(plan['required_edges']) == 3
    assert {eid for p in plan['parts'] for eid in p['edge_ids']} == {e['edge_id'] for e in plan['required_edges']}


def test_many_short_requirements_cannot_create_an_unreturnable_edge_list():
    import json
    from lib.scenario_coverage_contract import fingerprint,contract
    ledger=make_ledger(30)
    for r in ledger['requirements']['requirements']:r['requirement_id']=fingerprint(r['requirement_id']);r['text']='a'
    plan=plan_global_review({'snapshot_id':'s','generation':1},ledger,capacity=6000)
    assert len(plan['parts']) > 1
    assert len({eid for p in plan['parts'] for eid in p['edge_ids']}) == 435
    for p in plan['parts']:
        minimal={'accept':True,'issues':[],'relations':[],'read_requirement_ids':p['requirement_ids'],'reviewed_edge_ids':p['edge_ids'],
            'requirement_states':[{'requirement_id':rid,'status':'covered'} for rid in p['requirement_ids']]}
        assert len(json.dumps(minimal,separators=(',',':')).encode()) <= contract()['defaults']['partition_output_tokens']
