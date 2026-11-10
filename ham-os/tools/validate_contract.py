#!/usr/bin/env python3
import hashlib,json,sys
p=sys.argv[1]; d=json.load(open(p)); f=d.get('memoryOS'); assert isinstance(f,dict)
assert f['specVersion']=='1.0-review.4'
assert f['specSha256']=='e379b9c5d1f9c72d7cddca5e537282ae1f0b1f5902b7ca340682202247930012'
assert str(f['phase']) in {'0','1','2','3','4','5','6'}
required={'enabled','ledgerDualWrite','eventSliceShadow','capsuleShadow','needGraphShadow','facetIsolationShadow','packShadow','dynamicPackBudget','executionProgressV1','feedbackLearningShadow','adapterAuthEnforce','apiContractV2Enforce','adapterV2Codex','adapterV2Hermes','adapterV2Xiaodai','adapterV2OpenClaw','hindsightOnlyEvaluation'}
assert required <= set(f) and all(isinstance(f[k],bool) for k in required)
print(f'contract=valid schema={d["schema"]} memoryOS.phase={f["phase"]} enabled={f["enabled"]} sha256={hashlib.sha256(open(p,"rb").read()).hexdigest()}')
