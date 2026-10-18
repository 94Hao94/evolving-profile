import {afterEach,expect,it,vi} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {NextIntlClientProvider} from 'next-intl';
import en from '@/messages/en.json';
import {OperationalLaneCard} from '@/components/operational-overview';

afterEach(()=>vi.unstubAllGlobals());

it('renders an unavailable service HTTP status without replaceAll crashing the whole page',()=>{
 const html=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale:'en',timeZone:'UTC',messages:en,
  children:createElement(OperationalLaneCard,{lane:{id:'service',state:'critical',incidentCount:0,label:'Services',summary:'unavailable',detail:'',lastObservedAt:null,
    checks:[{label:'Controller',state:'critical',detail:501 as any,at:null}]},pipeline:{state:'unknown',failedMemories:null,pendingMemories:null},acknowledged:false,
    onDetail:()=>{},onToggleAcknowledgement:async()=>{},disabled:false})}));
 expect(html).toContain('501');expect(html).toContain('Controller');
});

it('unavailable optional guidance does not erase stats or fabricate zero model/candidate totals',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.includes('/models')
  ? new Response('<html>not configured</html>',{status:501})
  : Response.json({error:'guidance_unavailable'},{status:503})));
 const {loadGuidanceStats}=await import('@/lib/optional-guidance-stats');
 const result=await loadGuidanceStats();
 expect(result.models).toEqual({active:null,candidates:null,archived:null});
 expect(result.readiness.total).toBeNull();expect(result.readiness.states).toEqual({});
});

it('retains actual zero counts and observed candidate states from a healthy optional source',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.includes('/models')
  ? Response.json({counts:{active:0,candidates:2,archived_legacy:1}})
  : Response.json({total:2,items:[{state:'held'},{state:'held'}]})));
 const {loadGuidanceStats}=await import('@/lib/optional-guidance-stats');
 const result=await loadGuidanceStats();
 expect(result.models).toEqual({active:0,candidates:2,archived:1});
 expect(result.readiness).toEqual({total:2,states:{held:2}});
});

it('keeps an available model projection when candidate parsing fails',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.includes('/models')
  ? Response.json({counts:{active:3}})
  : new Response('<!DOCTYPE html>',{status:200})));
 const {loadGuidanceStats}=await import('@/lib/optional-guidance-stats');
 const result=await loadGuidanceStats();
 expect(result.models.active).toBe(3);expect(result.readiness.total).toBeNull();
});

it('counts observed state names without inheriting object prototype properties',async()=>{
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.includes('/models')
  ? Response.json({counts:{active:0}})
  : Response.json({total:3,items:[{state:'constructor'},{state:'__proto__'},{state:'held'}]})));
 const {loadGuidanceStats}=await import('@/lib/optional-guidance-stats');
 const result=await loadGuidanceStats();
 expect(Object.entries(result.readiness.states)).toEqual([['constructor',1],['__proto__',1],['held',1]]);
});
