try:
    from lib.scenario_hierarchical_plan import plan_hierarchical_work
except ImportError:plan_hierarchical_work=None


def test_actual_envelope_and_expected_output_can_pause_even_tiny_source():
    assert plan_hierarchical_work is not None
    result=plan_hierarchical_work({}, {'partitions':[{'primary':[{'text':'hi'}]}]}, {},
        {'counting':'conservative_utf8_bytes','input_bound':100,'output_bound':2000,'envelope_bytes':1000},
        {'partition_input_tokens':100,'partition_output_tokens':2000})
    assert result['status']=='capacity_paused'
    assert result['minimum_requests']>=2


def test_tree_converges_and_never_claims_all_pairs_or_token_accuracy():
    assert plan_hierarchical_work is not None
    result=plan_hierarchical_work({}, {'partitions':[{'primary':[{'text':'x'}]}]*13}, {},
        {'input_bound':20000,'output_bound':2000,'envelope_bytes':1000},
        {'partition_input_tokens':6000,'partition_output_tokens':2000})
    assert result['status']=='planned'
    assert result['minimum_requests']>=26
    assert result['cross_scope_exhaustiveness']=='not_exhaustive'
    assert result['counting']=='conservative_utf8_bytes'
    assert result['exact_total_requests'] is None
