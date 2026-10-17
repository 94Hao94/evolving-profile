import {describe,expect,it} from 'vitest';
import {resolveTopologyLayout} from '@/lib/topology-layout';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {TopologyEngineLab} from '@/components/topology-engine-lab';
import {buildTopologySpec} from '@/lib/topology-spec';

describe('topology default and saved layout',()=>{
  it('uses the user-calibrated positions without a browser override',()=>{
    const value=resolveTopologyLayout(null);
    expect(value.context).toEqual({x:69.4,y:8.7,width:13.3,height:8});
    expect(value['agent-process-memory-process-retrieval']).toEqual({x:31.4,y:67.2,width:11.4,height:4});
    expect(value['label-user-lane']).toEqual({x:6.5,y:35,width:13,height:4.2});
  });
  it('preserves valid custom positions and fills only missing default nodes',()=>{
    const custom={context:{x:62,y:8,width:15,height:8}};
    const value=resolveTopologyLayout(custom);
    expect(value.context).toEqual(custom.context);
    expect(value['external-rag-vector']).toEqual({x:32.4,y:87.1,width:9.7,height:6.2});
    expect(custom).toEqual({context:{x:62,y:8,width:15,height:8}});
  });
  it.each([[],null,'broken',42,{context:{x:NaN,y:4,width:8,height:4}},
    {context:{x:99,y:2,width:8,height:4}},{context:{x:5,y:5,width:0,height:4}}])('falls back for malformed or invisible saved anchors (%j)',saved=>{
    expect(resolveTopologyLayout(saved).context).toEqual({x:69.4,y:8.7,width:13.3,height:8});
  });
  it('never mutates the shared default on later edits',()=>{
    const first=resolveTopologyLayout(null);first.context.x=1;
    expect(resolveTopologyLayout(null).context.x).toBe(69.4);
  });
  it.each([false,true])('actually renders the calibrated anchors before browser hydration (%s)',english=>{
    const nodes=buildTopologySpec({english,summaries:new Map(),sourceScope:'test'}).nodes;
    const html=renderToStaticMarkup(createElement(TopologyEngineLab,{nodes,english}));
    const context=html.match(/<foreignObject\b[^>]*data-node-id="context"[^>]*>/)?.[0] || '';
    const agent=html.match(/<foreignObject\b[^>]*data-node-id="agent-process-memory-process-retrieval"[^>]*>/)?.[0] || '';
    expect(Number(context.match(/\bx="([^"]+)"/)?.[1])).toBeCloseTo(1160.368,4);
    expect(Number(agent.match(/\by="([^"]+)"/)?.[1])).toBeCloseTo(632.352,4);
    expect(html).toContain(english?'Open receipt: Agent Recall':'打开回执：智能体召回');
  });
});
