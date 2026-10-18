import {expect,it} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {NextIntlClientProvider} from 'next-intl';
import {readFileSync} from 'node:fs';
import {CoverageStatusCard} from '@/components/scenario-coverage-details';
import * as details from '@/components/scenario-coverage-details';
import {ScenarioCoverageSettings} from '@/components/scenario-coverage-settings';

function render(locale:string,child:any){
 const messages=JSON.parse(readFileSync(new URL(`../../src/messages/${locale}.json`,import.meta.url),'utf8'));
 return renderToStaticMarkup(createElement(NextIntlClientProvider,{locale,messages,timeZone:'Asia/Shanghai',children:child}));
}
it.each(['en','zh-CN'])('shows non-exhaustive scope and unknown counts without fake green in %s',locale=>{
 const html=render(locale,createElement(CoverageStatusCard,{data:{coverage_contract:'hierarchical_review.v1',status:'relation_pending',
   source_manifest_complete:true,coverage:{intent_review:'complete',target_complete:false,discovery_procedure_coverage:'partial'},
   unresolved_count:null,unread_count:null,scope:{session_id:'s'},model_calls:0}}));
 expect(html).toContain(locale==='zh-CN'?'未穷举全部关系':'Relationships are not exhaustive');
 expect(html).toContain(locale==='zh-CN'?'逐意图审查':'Intent review');
 expect(html).toContain(locale==='zh-CN'?'未知':'Unknown');
 expect(html).not.toContain(locale==='zh-CN'?'声明范围审查通过':'Declared scope reviewed');
});
it.each(['en','zh-CN'])('one protocol selector keeps old default and no new stage switches in %s',locale=>{
 const html=render(locale,createElement(ScenarioCoverageSettings,{value:{},onChange:()=>{},onSave:async()=>({})}));
 expect(html).toContain('name="review_protocol"');
 expect(html).toContain(locale==='zh-CN'?'分层证据审查':'Hierarchical evidence review');
 expect(html).toContain('value="segment_coverage.v1" selected');
});
it('shows reviewed subscopes without a contradictory legacy semantic status',()=>{
 const html=render('en',createElement(CoverageStatusCard,{data:{coverage_contract:'hierarchical_review.v1',status:'scope_reviewed',
  source_manifest_complete:true,coverage:{target_complete:true,intent_review:'complete',discovery_procedure_coverage:'complete',
   groups:{leaf:{status:'scope_reviewed'},other:{status:'relation_pending'}}},model_calls:0}}));
 expect(html).toContain('Source groups');
 expect(html).not.toContain('Not reviewed');
});
it('all relation endpoints have an original-source action',()=>{
 expect(details).toHaveProperty('RelationRows');
 const Component=(details as any).RelationRows;
 const html=render('zh-CN',createElement(Component,{rows:[{type:'obligation',state:'open',
  atom_ids:['a'.repeat(64),'b'.repeat(64),'c'.repeat(64)],evidence_quote:'保留三个关联端点'}],onRead:()=>{}}));
 expect((html.match(/<button/g)||[]).length).toBe(3);
});
it('explains model and protocol invalidation instead of showing a current reviewed group',()=>{
 const html=render('en',createElement(CoverageStatusCard,{data:{coverage_contract:'hierarchical_review.v1',status:'stale',
  source_manifest_complete:true,coverage:{target_complete:false,intent_review:'stale',groups:{old:{status:'stale'}}}}}));
 expect(html).toContain('model or protocol');
 expect(html).not.toContain('Declared scope reviewed');
});
it.each(['en','zh-CN'])('shows attributed but unresolved content without implying task success in %s',locale=>{
 const html=render(locale,createElement(CoverageStatusCard,{data:{coverage_contract:'hierarchical_review.v1',status:'relation_pending',
  source_manifest_complete:true,coverage:{attribution_review:'complete',scope_review:'unresolved',task_outcome:'not_verified',target_complete:false},
  context_original_pages_materialized:2}}));
 for(const word of locale==='zh-CN'?['原话与意图归属','对象与项目范围','外部成果未核验','后台原文补读页数']:['Conversation attribution','Object and project scope','External outcome not verified','Background original context pages'])expect(html).toContain(word);
 expect(html).not.toContain(locale==='zh-CN'?'声明范围审查通过':'Declared scope reviewed');
});
it('does not turn unknown context or scope into zero or reviewed',()=>{
 const html=render('en',createElement(CoverageStatusCard,{data:{coverage_contract:'hierarchical_review.v1',status:'local_candidate',coverage:{},context_original_pages_materialized:null}}));
 expect(html).toContain('Object and project scope');
 expect(html).toContain('Unknown / not measured');
 expect(html).not.toContain('Scope reviewed');
});
it.each(['en','zh-CN'])('labels legacy acceptance as compatibility, not new scope verification in %s',locale=>{
 const html=render(locale,createElement(CoverageStatusCard,{data:{coverage_contract:'hierarchical_review.v1',status:'scope_reviewed',
  coverage:{target_complete:true,scope_review:'not_reviewed',scope_axes_complete:false,groups:{leaf:{status:'scope_reviewed'}}}}}));
 expect(html).toContain(locale==='zh-CN'?'旧格式兼容':'Legacy compatibility');
 expect(html).not.toContain(locale==='zh-CN'?'声明范围审查通过':'Declared scope reviewed');
});
it.each(['en','zh-CN'])('shows bounded repair and measured capacity without claiming acceptance in %s',locale=>{
 const html=render(locale,createElement(CoverageStatusCard,{data:{coverage_contract:'hierarchical_review.v1',status:'intent_gap',coverage:{},
  processing_diagnostics:{format_reselections:1,repair_model_calls:1,transport_windows:3,max_extract_wire_bytes:5800,source_scope_reduced:false}}}));
 expect(html).toContain(locale==='zh-CN'?'结构格式重选':'Structural format reselections');
 expect(html).toContain(locale==='zh-CN'?'完整请求容量':'Complete request capacity');
 expect(html).toContain('5800');
 expect(html).not.toContain(locale==='zh-CN'?'声明范围审查通过':'Declared scope reviewed');
});
it.each(['en','zh-CN'])('shows protocol-specific full-request input guard and unchanged raw/output limits in %s',locale=>{
 const html=render(locale,createElement(ScenarioCoverageSettings,{value:{review_protocol:'hierarchical_review.v1'},onChange:()=>{},onSave:async()=>({})}));
 expect(html).toContain('max="12000"');expect(html).toContain('value="12000"');
 expect(html).toContain(locale==='zh-CN'?'完整请求':'complete request');
 const old=render(locale,createElement(ScenarioCoverageSettings,{value:{},onChange:()=>{},onSave:async()=>({})}));
 expect(old).toContain('max="6000"');expect(old).not.toContain('max="12000"');
});
it.each(['en','zh-CN'])('explains foreign-protocol navigation without a false zero usage claim in %s',locale=>{
 const html=render(locale,createElement(CoverageStatusCard,{data:{coverage_contract:'segment_coverage.v1',review_protocol:'segment_coverage.v1',
  status:'global_pending',reason:'review_protocol_changed',receipt_review_protocol:'hierarchical_review.v1',
  source_manifest_complete:true,semantic_review_status:'not_reviewed',model_calls:null}}));
 expect(html).toContain(locale==='zh-CN'?'其他协议的核验结果不计入当前状态':'verdicts from another protocol are not applied here');
 expect(html).not.toContain('review_protocol_changed');
 expect(html).toContain(locale==='zh-CN'?'全局语义审查待完成':'Global semantic review pending');
 expect(html).not.toContain(locale==='zh-CN'?'未准备或暂不可用':'Unavailable / not prepared');
 expect(html).not.toContain(locale==='zh-CN'?'额外模型请求为零':'No additional model requests');
});
