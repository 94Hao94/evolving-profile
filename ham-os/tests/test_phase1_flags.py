import json,os
from pathlib import Path
import pytest
def test_phase1_shadow_enables_only_ledger_dual_write():
 path=os.environ.get('HAM_CONTRACT')
 if not path: pytest.skip('phase1 fixture not selected')
 f=json.loads(Path(path).read_text())['memoryOS']
 assert f['phase']=='1' and f['enabled'] and f['ledgerDualWrite']
 assert not any(f[k] for k in ('eventSliceShadow','capsuleShadow','needGraphShadow','packShadow','adapterV2Codex','hindsightOnlyEvaluation'))
