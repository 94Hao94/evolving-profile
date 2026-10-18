try:
    from lib.scenario_relation_obligations import build_discovery_tasks,validate_relation_proposal,assess_hierarchical_scope
except ImportError:build_discovery_tasks=None
from lib.scenario_hierarchical_review import build_review_request,execute_review
from test_scenario_hierarchical_review import budget,accepted


def reviewed(tmp_path,stage,inputs,result=None):
    req=build_review_request(stage,{'protocol':'hierarchical_review.v1','snapshot_id':'s'},inputs,
        {'partition_input_tokens':20000,'partition_output_tokens':2000})
    def provider(payload):
        r=accepted(payload)
        if stage=='merge':r['result'].update(discovery_complete=True,obligations=[],object_links=[])
        if result:r['result'].update(result)
        return r
    return execute_review(req,provider,budget(tmp_path),source_current=lambda:True,authorize_request=lambda:None)


def test_unresolved_group_does_not_green_or_block_peer(tmp_path):
    assert build_discovery_tasks is not None
    manifest={'binding':{'protocol':'hierarchical_review.v1','snapshot_id':'s'},'source_complete':True,
        'groups':{'A':['a'],'B':['b']},'atom_ids':['a','b'],'residual_ids':[],
        'leaf_partition_ids':['p'],'discovery_task_ids':['d']}
    leaves=[reviewed(tmp_path/'l','leaf',{'partition':{'partition_id':'p','primary':[]},'proposal':{}})]
    discovery=[reviewed(tmp_path/'d','merge',{'task_id':'d','atoms':[{'atom_id':'a'},{'atom_id':'b'}]})]
    obligation={'obligation_id':'o','atom_ids':['b'],'state':'open','reason':'object ambiguous','evidence_refs':[]}
    result=assess_hierarchical_scope(manifest,leaves,discovery,[obligation],{'allowed':True})
    assert result['groups']['A']['status']=='scope_reviewed'
    assert result['groups']['B']['status']=='relation_pending'
    assert result['target_complete'] is False
    assert result['cross_scope_exhaustiveness']=='not_exhaustive'


def test_plain_accepted_receipts_do_not_prove_coverage():
    assert build_discovery_tasks is not None
    m={'binding':{},'source_complete':True,'groups':{'A':['a']},'atom_ids':['a'],
       'residual_ids':[],'leaf_partition_ids':['p'],'discovery_task_ids':['d']}
    result=assess_hierarchical_scope(m,[{'accept':True}],[{'accept':True}],[],{'allowed':True})
    assert result['target_complete'] is False
    assert result['discovery_procedure_coverage']!='complete'


def test_closing_relation_needs_actual_exact_source_not_similarity():
    assert build_discovery_tasks is not None
    task={'atom_ids':['a','b']}
    proposal={'obligations':[{'obligation_id':'o','atom_ids':['a','b'],'state':'supported','reason':'same school',
        'evidence_refs':[]}],'object_links':[]}
    result=validate_relation_proposal(task,proposal,[])
    assert result['obligations'][0]['state']=='open'
    proposal['obligations'][0]['evidence_refs']=[{'page_id':'x','quote':'explicit correction'}]
    assert validate_relation_proposal(task,proposal,[])['obligations'][0]['state']=='open'


def test_discovery_includes_residuals_and_all_boundaries():
    assert build_discovery_tasks is not None
    value=build_discovery_tasks({'snapshot_id':'s'}, {'atoms':[{'atom_id':'a'}],
        'residuals':[{'atom_id':'r','reason':'unclassified'}],'boundaries':[{'node_id':'n','children':['x','y']}]}, {})
    assert set(value['required_ids'])=={'a','r'}
    assert value['boundaries'][0]['node_id']=='n'
