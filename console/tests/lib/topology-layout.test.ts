import {describe,expect,it} from 'vitest';
import {resolveTopologyLayout} from '@/lib/topology-layout';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {TopologyEngineLab} from '@/components/topology-engine-lab';
import {buildTopologySpec} from '@/lib/topology-spec';

describe('topology default and saved layout',()=>{
  it('uses the user-calibrated positions without a browser override',()=>{
    const value=resolveTopologyLayout(null);
    expect(value.context).toEqual({x:69.413347,y:8.606865,width:13.798938,height:8.093135});
    expect(value['agent-process-memory-process-retrieval']).toEqual({x:31.362031,y:66.80061,width:11.462031,height:4.3991});
    expect(value['label-user-lane'].x).toBeCloseTo(14.65311,5);
  });
  it('preserves valid custom positions and fills only missing default nodes',()=>{
    const custom={context:{x:62,y:8,width:15,height:8}};
    const value=resolveTopologyLayout(custom);
    expect(value.context).toEqual(custom.context);
    expect(value['external-rag-vector'].y).toBeCloseTo(86.872245,5);
    expect(custom).toEqual({context:{x:62,y:8,width:15,height:8}});
  });
  it('restores the same anchors from an installation-shared layout envelope',()=>{
    const shared={schema:'evolving-profile.topology-layout.v1',revision:3,canvas:{width:1672,height:941,asset:'topology-reference-design-v17'},anchors:{context:{x:62,y:8,width:15,height:8}}};
    expect(resolveTopologyLayout(shared).context).toEqual({x:62,y:8,width:15,height:8});
  });
  it('places lane headings beside their icons and overlay root cards on their actual vector boxes',()=>{
    const layout=resolveTopologyLayout(null);
    // Canonical bitmap/vector coordinates, independent of CSS viewport width.
    expect(layout['label-user-lane'].x*1672/100).toBeCloseTo(245,3);
    expect(layout['label-user-lane'].y*941/100).toBeCloseTo(259,3);
    expect(layout['agent-process-memory-observe-trajectory'].x*1672/100).toBeCloseTo(330,3);
    expect(layout['rag-root'].width*1672/100).toBeCloseTo(164,3);
  });
  it.each([[],null,'broken',42,{context:{x:NaN,y:4,width:8,height:4}},
    {context:{x:99,y:2,width:8,height:4}},{context:{x:5,y:5,width:0,height:4}}])('falls back for malformed or invisible saved anchors (%j)',saved=>{
    expect(resolveTopologyLayout(saved).context).toEqual({x:69.413347,y:8.606865,width:13.798938,height:8.093135});
  });
  it('never mutates the shared default on later edits',()=>{
    const first=resolveTopologyLayout(null);first.context.x=1;
    expect(resolveTopologyLayout(null).context.x).toBe(69.413347);
  });
  it.each([false,true])('actually renders the calibrated anchors before browser hydration (%s)',english=>{
    const nodes=buildTopologySpec({english,summaries:new Map(),sourceScope:'test'}).nodes;
    const html=renderToStaticMarkup(createElement(TopologyEngineLab,{nodes,english}));
    const context=html.match(/<foreignObject\b[^>]*data-node-id="context"[^>]*>/)?.[0] || '';
    const agent=html.match(/<foreignObject\b[^>]*data-node-id="agent-process-memory-process-retrieval"[^>]*>/)?.[0] || '';
    expect(Number(context.match(/\bx="([^"]+)"/)?.[1])).toBeCloseTo(1160.591157,3);
    expect(Number(agent.match(/\by="([^"]+)"/)?.[1])).toBeCloseTo(628.593739,3);
    expect(html).toContain(english?'Open receipt: Agent Recall':'打开回执：智能体召回');
  });
});
