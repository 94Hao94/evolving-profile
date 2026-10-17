import {expect,it} from 'vitest';
import {normalizeCoverageSettings,coverageRegistry,coverageSummary} from '@/lib/scenario-coverage';
it('preserves old default and gates new enforced protocol without granting money',()=>{
 expect(normalizeCoverageSettings().review_protocol).toBe('segment_coverage.v1');
 expect(normalizeCoverageSettings({review_protocol:'hierarchical_review.v1'}).mode).toBe('source_shadow');
 expect(()=>normalizeCoverageSettings({review_protocol:'hierarchical_review.v1',mode:'enforced'})).toThrow();
});
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {NextIntlClientProvider} from 'next-intl';
import {readFileSync} from 'node:fs';
import {CoverageStatusCard} from '@/components/scenario-coverage-details';

it('defaults to source shadow without model calls, and rejects uncontrolled budgets',()=>{
 expect(normalizeCoverageSettings()).toEqual({mode:'source_shadow',limits:{},model_trial:false,review_protocol:'segment_coverage.v1'});
 expect(()=>normalizeCoverageSettings({mode:'assisted',limits:{model_requests:100}})).toThrow();
 expect(()=>normalizeCoverageSettings({mode:'assisted',model_trial:'true'})).toThrow();
 expect(coverageRegistry.defaults.model_requests).toBe(0);
});
it.each(['en','zh-CN','de'])('renders truthful source-only coverage with locale %s',locale=>{
 const messages=JSON.parse(readFileSync(new URL(`../../src/messages/${locale}.json`,import.meta.url),'utf8'));
 const html=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale,messages,timeZone:'Asia/Shanghai',children:createElement(CoverageStatusCard,{data:{status:'global_pending',source_manifest_complete:true,semantic_review_status:'not_reviewed',requirement_count:3,has_unread_requirements:true,model_calls:0}})}));
 expect(html).toContain(locale==='zh-CN'?'尚未语义审查':'Not reviewed');
 expect(html).toContain(locale==='zh-CN'?'没有新增模型请求':'No additional model requests');
 if(locale!=='zh-CN')expect(html).not.toMatch(/[\u3400-\u9fff]/u);
});
it('projects structure and semantics separately rather than a misleading complete label',()=>{
 const s=coverageSummary({status:'global_pending',source_manifest_complete:true,semantic_review_status:'not_reviewed',requirement_count:3});
 expect(s.structureComplete).toBe(true);expect(s.semanticAccepted).toBe(false);expect(s.requirements).toBe(3);
 expect(coverageSummary({status:'accepted',semantic_review_status:'not_reviewed'}).semanticAccepted).toBe(false);
});
