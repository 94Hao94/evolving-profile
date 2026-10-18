import pytest
from test_scenario_coverage_partition import snapshot
from lib.scenario_coverage_contract import validate_settings,canonical
from lib.scenario_coverage_partition import partition_snapshot,validate_partition
from lib.scenario_hierarchical_review import build_review_request
from lib.scenario_coverage_provider import ConfiguredCoverageProvider
from lib.scenario_hierarchical_plan import plan_hierarchical_work


def provider():
    return ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid',
        'EVOLVING_PROFILE_API_LLM_API_KEY':'not-real'},opener=lambda *a,**kw:pytest.fail('capacity planning must not call network'))


def prepare(*args):
    from lib.scenario_hierarchical_capacity import prepare_review_windows
    return prepare_review_windows(*args)


def test_complete_wire_adaptation_preserves_every_source_character_role_and_final_condition(tmp_path):
    text=('引用{"a":"🙂中文\\x"}。 Do not publish.\n'*180)+'最后条件：仅限草稿，不得覆盖原件。'
    s=snapshot(tmp_path,text);limits=validate_settings({'review_protocol':'hierarchical_review.v1','limits':{'partition_input_tokens':6000}})['limits']
    initial=partition_snapshot(s,capacity=2000,context_tokens=512);p=provider()
    binding={k:s[k] for k in ('snapshot_id','generation','scope','permission','selection_version','normalization_version')}
    prepared=prepare(s,initial,binding,limits,p)
    assert prepared['status']=='planned'
    assert validate_partition(prepared['plan'],s)['complete'] is True
    assert ''.join(span['text'] for part in prepared['plan']['partitions'] for span in part['primary'] if span['role']=='user')==text
    assert all(len(canonical(p.request_envelope(build_review_request('extract',binding,{'partition':part},limits))))<=6000 for part in prepared['plan']['partitions'])
    capability={'input_bound':6000,'output_bound':2000,'envelope_bytes':1800,'wire_input_sizes':prepared['wire_input_sizes']}
    work=plan_hierarchical_work(s,prepared['plan'],{},capability,limits)
    assert work['status']=='planned' and work['input_measurement']=='full_configured_wire_bytes'
    assert work['minimum_requests']>=3


def test_even_minimal_protocol_overhead_stays_paused_without_cutting_source(tmp_path):
    s=snapshot(tmp_path,'Never delete原件🙂。');limits=validate_settings({'review_protocol':'hierarchical_review.v1'})['limits']
    limits['partition_input_tokens']=500
    initial=partition_snapshot(s,capacity=2000)
    out=prepare(s,initial,{},limits,provider())
    assert out['status']=='capacity_paused' and validate_partition(out['plan'],s)['complete']
    assert out['adaptation']['source_scope_reduced'] is False


def test_actual_wire_measurement_cannot_be_malformed_or_hide_a_partition(tmp_path):
    s=snapshot(tmp_path,'检查而已');parts=partition_snapshot(s,capacity=1000)
    limits=validate_settings()['limits']
    for sizes in [[],['small'],[-1],[True]]:
        with pytest.raises(ValueError):plan_hierarchical_work(s,parts,{}, {'wire_input_sizes':sizes},limits)


def test_measured_wire_is_exact_executor_selected_provider_request(tmp_path):
    from lib.scenario_coverage_incremental import _provider_binding
    s=snapshot(tmp_path,'仅检查，不发布。'*110);limits=validate_settings()['limits'];p=provider()
    binding={'scope':s['scope'],'provider':_provider_binding(p)}
    prepared=prepare(s,partition_snapshot(s,capacity=2000),binding,limits,p)
    actual=[len(canonical(p.request_envelope(build_review_request('extract',
        {**binding,'selected_provider':_provider_binding(p)},{'partition':part},limits))))
        for part in prepared['plan']['partitions']]
    assert prepared['wire_input_sizes']==actual


def test_frozen_adaptation_plan_is_reproduced_from_original_execution_partitions(tmp_path):
    from lib.scenario_hierarchical_capacity import prepare_review_work
    s=snapshot(tmp_path,'Never delete原件🙂。'*240);limits=validate_settings()['limits'];p=provider()
    first=prepare_review_work(s,limits,p)
    replay=prepare_review_work(s,limits,p,first['source_partitions'])
    assert replay['plan']==first['plan']
    assert replay['partitions']==first['partitions']
