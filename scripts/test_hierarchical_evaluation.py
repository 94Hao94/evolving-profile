import importlib.util
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host-adapter'))
try:
    from hierarchical_comparison import evaluate_hierarchical_case
except ImportError:evaluate_hierarchical_case=None


def test_missing_answer_witness_cannot_pass_benefit():
    assert evaluate_hierarchical_case is not None
    out=evaluate_hierarchical_case({'case_id':'x','requirements':[{'id':'q'}],'coverage':{'target_complete':True}})
    assert out['answer_benefit']=='not_measured'
    assert out['semantic_ready'] is False


def test_holdout_contamination_and_missing_cases_cannot_be_green():
    assert evaluate_hierarchical_case is not None
    result=evaluate_hierarchical_case({'holdout':True,'used_for_tuning':True,'requirements':[]})
    assert result['semantic_ready'] is False and 'holdout_used_for_tuning' in result['errors']


def test_declared_review_success_and_failure_cannot_both_pass():
    assert evaluate_hierarchical_case is not None
    case={'case_id':'x','status':'scope_reviewed','source_evidence_fresh':True,'requirements':[{'id':'a',
        'reference':{'independent':True,'reviewer':'reviewer','witness':'raw-source-review','source_ids':['s']},
        'semantic_review':{'preserved':True,'scope_correct':True,'witness':'comparison'}}],
        'coverage':{'coverage_contract':'hierarchical_review.v1','target_complete':True,'source_coverage':'complete',
        'intent_review':'complete','obligation_review':'complete','discovery_procedure_coverage':'complete',
        'attribution_review':'complete','scope_review':'resolved','scope_axes_complete':True,
        'cross_scope_exhaustiveness':'not_exhaustive','unresolved_count':0}}
    assert evaluate_hierarchical_case(case)['semantic_ready'] is True
    case['reason']='semantic_rejected'
    assert evaluate_hierarchical_case(case)['semantic_ready'] is False


def test_legacy_success_cannot_qualify_new_scope_axes_without_explicit_evidence():
    case={'case_id':'legacy','status':'scope_reviewed','source_evidence_fresh':True,'requirements':[{'id':'a',
        'reference':{'independent':True,'reviewer':'reviewer','witness':'raw-source-review','source_ids':['s']},
        'semantic_review':{'preserved':True,'scope_correct':True,'witness':'comparison'}}],
        'coverage':{'coverage_contract':'hierarchical_review.v1','target_complete':True,'source_coverage':'complete',
        'intent_review':'complete','obligation_review':'complete','discovery_procedure_coverage':'complete',
        'cross_scope_exhaustiveness':'not_exhaustive','unresolved_count':0}}
    assert evaluate_hierarchical_case(case)['semantic_ready'] is False


def test_preflight_without_execute_cannot_call_provider(tmp_path):
    file=Path(__file__).with_name('verify-hierarchical-review.py')
    assert file.is_file(),'preflight implementation missing'
    spec=importlib.util.spec_from_file_location('hierarchical_preflight',file)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    assert mod.authorized_execution({'minimum_requests':5,'max_reserved_tokens':100},
        {'max_requests':16,'requests_used':13,'max_tokens':128000,'charged_tokens':54365}) is False
    assert mod.authorized_execution({'minimum_requests':3,'max_reserved_tokens':20000},
        {'max_requests':16,'requests_used':13,'max_tokens':128000,'charged_tokens':54365}) is True


def test_acceptance_cli_ingests_frozen_hierarchical_evaluation(tmp_path):
    import json,subprocess
    from lib.scenario_coverage_contract import fingerprint,hierarchical_protocol_fingerprint
    root=Path(__file__).resolve().parents[1];evidence=tmp_path/'hierarchical';evidence.mkdir()
    protocol=hierarchical_protocol_fingerprint()
    manifest=[{'case_id':'case','snapshot_id':'s','requirements_sha256':fingerprint([])}]
    (evidence/'evaluation.json').write_text(json.dumps({'protocol_fingerprint':protocol,'case_manifest':manifest,
        'case_manifest_sha256':fingerprint(manifest),'cases':[{'case_id':'case','snapshot_id':'s','requirements':[],
        'validated_protocol_fingerprint':protocol}]}))
    out=subprocess.run([sys.executable,str(root/'scripts/verify-ep-acceptance.py'),
        '--evidence-root',str(tmp_path/'engineering'),'--hierarchical-root',str(evidence)],capture_output=True,text=True)
    assert out.returncode==2 and 'Traceback' not in out.stderr
    value=json.loads(out.stdout)
    assert value['hierarchical_case_count']==1 and value['hierarchical_semantic_ready'] is False


def test_cli_plan_uses_runtime_binding_and_actual_wire_without_provider_calls(tmp_path):
    from test_scenario_review_capacity_adaptation import provider
    from test_scenario_coverage_partition import snapshot
    from lib.scenario_coverage_contract import validate_settings
    from lib.scenario_coverage_partition import validate_partition
    from lib.scenario_hierarchical_capacity import prepare_review_work
    file=Path(__file__).with_name('verify-hierarchical-review.py')
    spec=importlib.util.spec_from_file_location('hierarchical_preflight_capacity',file)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    s=snapshot(tmp_path,'{"原文":"🙂\\路径"}。仅草稿。'*100);settings=validate_settings();p=provider()
    actual=mod.prepare_case(s,settings,p)
    expected=prepare_review_work(s,settings['limits'],p)
    assert actual==expected and actual['plan']['input_measurement']=='full_configured_wire_bytes'
    assert validate_partition(actual['partitions'],s)['complete']


def test_cli_execute_preserves_tuning_labels_and_frozen_runtime_plan(tmp_path,monkeypatch):
    import json,shutil
    from types import SimpleNamespace
    from test_scenario_hierarchical_end_to_end import setup,controlled
    from lib.scenario_coverage_contract import validate_settings,fingerprint
    from lib.scenario_hierarchical_store import HierarchicalStore
    state,store,s,_,_,budget=setup(tmp_path);calls=[];provider=controlled(calls)
    from lib.scenario_coverage_budget import CoverageBudget
    ledger=state/'evaluation-requests.sqlite3'
    budget=CoverageBudget(ledger,job_id='evaluation',budget_identity=s['semantic_budget_identity'],parent_attempts=0,
        max_requests=20,max_tokens=100000,scope_identity='isolated_fixture')
    spec=importlib.util.spec_from_file_location('hierarchical_execute',Path(__file__).with_name('verify-hierarchical-review.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    monkeypatch.setattr(mod,'configured_provider',lambda _:provider)
    monkeypatch.setattr(mod,'coverage_permission',lambda _:s['permission'])
    monkeypatch.setattr(mod,'_rows',lambda _:[s['scope']])
    work=mod.prepare_case(s,validate_settings({'review_protocol':'hierarchical_review.v1'}),provider)
    output=tmp_path/'evaluation';folder=output/'cases/case';folder.mkdir(parents=True)
    shutil.copy2(state/'coverage.sqlite3',folder/'coverage.sqlite3')
    chosen={'name':'case','session_id':s['scope']['session_id'],'snapshot_id':s['snapshot_id'],'holdout':False,'used_for_tuning':True,
        'minimum_requests':work['plan']['minimum_requests'],'max_reserved_tokens':42000,'plan':work['plan']}
    plan={'cases':[chosen],'protocol_fingerprint':mod._protocol_fingerprint(),'shared_grant_ledger':str(ledger)}
    plan['plan_sha256']=fingerprint(plan);(output/'plan.json').write_text(json.dumps(plan))
    result=mod.execute(SimpleNamespace(output=output,case='case',expected_plan_sha256=plan['plan_sha256'],grant_ledger=ledger,state_root=state))
    assert result['used_for_tuning'] is True and len(calls)>=3
    graph=HierarchicalStore(folder/'hierarchical/graphs.sqlite3',readonly=True).load_current(s['scope'],s['permission'])['graph']
    assert graph['plan']==chosen['plan']
