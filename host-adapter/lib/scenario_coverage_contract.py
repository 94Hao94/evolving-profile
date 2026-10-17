"""Single registry for coverage contracts, modes and resource limits."""
import hashlib
import json
from pathlib import Path


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()


def fingerprint(value):return hashlib.sha256(canonical(value)).hexdigest()


def hierarchical_protocol_fingerprint(root=None):
    root=Path(root) if root is not None else Path(__file__).resolve().parents[2]
    names={str(p.relative_to(root)) for p in (root/'host-adapter/lib').glob('scenario_hierarchical*.py')}
    names.update('host-adapter/lib/'+n+'.py' for n in ('scenario_intent_atoms','scenario_evidence_capsule',
        'scenario_relation_obligations','scenario_source_codec','scenario_coverage_store','scenario_coverage_budget',
        'scenario_coverage_provider','scenario_coverage_contract','scenario_coverage_partition','scenario_raw_readback'))
    names.update({'config/scenario-coverage-contract.json','host-adapter/hierarchical_comparison.py'})
    return fingerprint([(name,hashlib.sha256((root/name).read_bytes()).hexdigest()) for name in sorted(names)])


def contract():
    path=Path(__file__).resolve().parents[2]/'config/scenario-coverage-contract.json'
    value=json.loads(path.read_text())
    if value.get('schema')!='segment_coverage.v1':raise ValueError('coverage_contract_unavailable')
    return value


def validate_settings(settings=None):
    registry=contract();settings=settings or {}
    if not isinstance(settings,dict) or set(settings)-{'mode','limits','model_trial','review_protocol'}:raise ValueError('coverage_settings_invalid')
    mode=settings.get('mode',registry['mode'])
    if mode not in registry['modes']:raise ValueError('coverage_mode_invalid')
    protocol=settings.get('review_protocol',registry['default_review_protocol'])
    if not isinstance(protocol,str) or protocol not in registry['review_protocols']:raise ValueError('coverage_protocol_invalid')
    if protocol=='hierarchical_review.v1' and mode=='enforced':raise ValueError('hierarchical_enforced_unavailable')
    defaults={**registry['defaults'],**registry['review_protocols'][protocol].get('defaults',{})};limits=dict(defaults)
    overrides=settings.get('limits',{})
    if not isinstance(overrides,dict) or set(overrides)-set(registry['editable_limits']):raise ValueError('coverage_limits_invalid')
    for key,value in overrides.items():
        if type(value) is not int or not registry.get('minimum_limits',{}).get(key,1)<=value<=defaults[key]:raise ValueError('coverage_limits_invalid')
        limits[key]=value
    trial=settings.get('model_trial',False)
    if type(trial) is not bool:raise ValueError('coverage_trial_invalid')
    # Positive budgets require an explicit trial and a non-shadow mode.
    limits['model_requests']=defaults['pilot_requests'] if trial and mode!='source_shadow' else 0
    limits['model_tokens']=defaults['pilot_tokens'] if trial and mode!='source_shadow' else 0
    return {'mode':mode,'limits':limits,'model_trial':trial,'contract_schema':protocol,'review_protocol':protocol}


def coverage_permission(state_root):
    """Permission version excludes Provider keys and unrelated UI settings."""
    from .context_incremental import summary_runtime_permission
    proof=summary_runtime_permission(state_root)
    if proof['status']=='unknown':return {'allowed':False,'version':'unknown'}
    return {'allowed':proof['allowed'],'version':fingerprint({'policy':'coverage-permission.v1','allowed':proof['allowed']})}
