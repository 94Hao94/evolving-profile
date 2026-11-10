import json, os
from pathlib import Path
REQUIRED={'enabled','ledgerDualWrite','eventSliceShadow','capsuleShadow','needGraphShadow','facetIsolationShadow','packShadow','dynamicPackBudget','executionProgressV1','feedbackLearningShadow','adapterAuthEnforce','apiContractV2Enforce','adapterV2Codex','adapterV2Hermes','adapterV2Xiaodai','adapterV2OpenClaw','hindsightOnlyEvaluation'}

def test_phase0_flags_are_complete_and_all_false():
    configured = os.environ.get('HAM_CONTRACT')
    p = Path(configured) if configured else Path.home()/'.evolving-profile/memory-contract-v5.json'
    if not p.is_file():
        p = Path.home()/'.hindsight/memory-contract-v5.json'
    flags=json.loads(p.read_text())['memoryOS']
    assert REQUIRED <= set(flags)
    if flags['phase'] != '0':
        import pytest; pytest.skip('Phase0 fixture not selected')
    assert all(flags[name] is False for name in REQUIRED)
    assert flags['phase']=='0'
    assert flags['specVersion']=='1.0-review.4'
