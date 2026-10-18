import {it,expect} from 'vitest';
import * as budgets from '@/lib/scenario-coverage';

it('protocol limits share one registry while honoring explicit tighter bounds',()=>{
 expect(budgets.normalizeCoverageSettings({limits:{partition_input_tokens:6000}}).limits.partition_input_tokens).toBe(6000);
 expect(()=>budgets.normalizeCoverageSettings({limits:{partition_input_tokens:12000}})).toThrow();
 expect(budgets.normalizeCoverageSettings({review_protocol:'hierarchical_review.v1',limits:{partition_input_tokens:12000}}).limits.partition_input_tokens).toBe(12000);
 expect(()=>budgets.normalizeCoverageSettings({review_protocol:'hierarchical_review.v1',limits:{partition_input_tokens:12001}})).toThrow();
});
it('switching back cannot retain an illegal new-protocol cap or erase unrelated tighter settings',()=>{
 expect(budgets).toHaveProperty('switchCoverageProtocol');
 const next=(budgets as any).switchCoverageProtocol({mode:'source_shadow',model_trial:false,review_protocol:'hierarchical_review.v1',limits:{partition_input_tokens:12000,context_tokens:128,output_bytes:1234}},'segment_coverage.v1');
 expect(next.limits).toEqual({context_tokens:128,output_bytes:1234});
 expect(()=>budgets.normalizeCoverageSettings(next)).not.toThrow();
});
