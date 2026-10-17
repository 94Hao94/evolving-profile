import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('ep_gate',Path(__file__).with_name('verify-ep-acceptance.py'))
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)


def report():
    return {'source_fingerprint':'hash','source_unchanged_during_checks':True,'checks':[{'name':n,'exit_code':0} for n in gate.REQUIRED],
        'semantic_cases':[{'evaluation_scope':'full','source_structure_complete':True,'source_evidence_fresh':True,'validated_protocol_fingerprint':'protocol',
            'failure':None,'coverage':{'status':'accepted','semantic_review_status':'automated_declared_scope_accepted','source_manifest_complete':True,
                'missing_part_ids':[],'missing_local_partition_ids':[],'conflicts':[]},'external_fact_verified':False}]}


def test_passing_engineering_does_not_greenwash_missing_or_sampled_semantics():
    r=report();r['semantic_cases']=[]
    assert gate.assess(r,'hash','protocol')['release_ready'] is False
    r['semantic_cases']=[{'evaluation_scope':'sampled_first_last','coverage':{'status':'accepted'}}]
    assert gate.assess(r,'hash','protocol')['semantic_status']=='incomplete'


def test_failed_missing_duplicate_stale_or_changed_source_cannot_pass():
    for mutation in ['fail','missing','duplicate','changed']:
        r=report()
        if mutation=='fail':r['checks'][0]['exit_code']=1
        if mutation=='missing':r['checks'].pop()
        if mutation=='duplicate':r['checks'].append(r['checks'][0])
        out=gate.assess(r,'changed' if mutation=='changed' else 'hash','protocol')
        assert out['release_ready'] is False


def test_complete_declared_scope_can_pass_but_does_not_claim_model_adoption():
    out=gate.assess(report(),'hash','protocol')
    assert out['engineering_status']=='passed' and out['semantic_status']=='passed'
    assert out['answer_adoption']=='not_measured' and out['external_fact_verified'] is False


def test_legacy_accept_cannot_enable_hierarchical_protocol():
    assert gate.assess(report(),'hash','protocol').get('hierarchical_semantic_ready') is False


def test_hierarchical_self_attestation_or_missing_manifest_cannot_enable():
    r=report();r['hierarchical_evaluation']={'semantic_ready':True,'answer_benefit':'measured','cases':[]}
    out=gate.assess(r,'hash','protocol')
    assert out.get('hierarchical_semantic_ready') is False


def test_engineering_runner_includes_the_new_evaluation_cli_regressions(tmp_path,monkeypatch):
    from types import SimpleNamespace
    calls=[]
    def command(args,**kwargs):
        calls.append(args);kwargs['stdout'].write('isolated command boundary fixture\n')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(gate.subprocess,'run',command)
    gate.run_engineering(Path(__file__).resolve().parents[1],tmp_path)
    assert calls[0][1:3]==['-m','pytest']
    assert 'scripts/test_hierarchical_evaluation.py' in calls[0]


def test_boolean_exit_codes_and_malformed_evidence_are_not_success():
    r=report();r['checks'][0]['exit_code']=False
    assert gate.assess(r,'hash','protocol')['release_ready'] is False
    for r in [None,{'checks':['bad'],'semantic_cases':{}},{'checks':{},'semantic_cases':[None]}]:
        assert gate.assess(r,'hash','protocol')['release_ready'] is False


def test_contradiction_changed_source_and_stale_review_cannot_pass():
    for field,value in [('failure','source_changed'),('source_evidence_fresh',False),('validated_protocol_fingerprint','old')]:
        r=report();r['semantic_cases'][0][field]=value
        assert gate.assess(r,'hash','protocol')['release_ready'] is False
    for field,value in [('source_manifest_complete',False),('missing_part_ids',['missing']),('missing_local_partition_ids',['missing']),('conflicts',['conflict'])]:
        r=report();r['semantic_cases'][0]['coverage'][field]=value
        assert gate.assess(r,'hash','protocol')['release_ready'] is False
    r=report();r['source_unchanged_during_checks']=False
    assert gate.assess(r,'hash','protocol')['release_ready'] is False
    for malformed in [True,'accepted',['accepted']]:
        r=report();r['semantic_cases'][0]['coverage']=malformed
        assert gate.assess(r,'hash','protocol')['release_ready'] is False
