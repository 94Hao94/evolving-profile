import { expect, it } from 'vitest';
import { defaultTopologyLayout, topologyFailureView } from '@/lib/topology-layout';

it('switches to the requested locale even when GET and browser cache both fail',()=>{
  const layout=defaultTopologyLayout();layout.revision=3;
  layout.texts={en:{context:'English context'},zh:{context:'中文自定义上下文'}};
  const previous={layout,texts:layout.texts.zh};
  const fallback=topologyFailureView(previous,null,true);
  expect(fallback.texts).toEqual({context:'English context'});
  const savePayload={...fallback.layout,texts:{...fallback.layout.texts,en:fallback.texts}};
  expect(savePayload.texts.en).toEqual({context:'English context'});
  expect(savePayload.texts.zh).toEqual({context:'中文自定义上下文'});
});

it('keeps the newer in-memory geometry when the optional browser cache is stale',()=>{
  const current=defaultTopologyLayout();current.revision=3;current.anchors.context={x:62,y:8,width:15,height:8};
  const cached=defaultTopologyLayout();cached.revision=1;
  expect(topologyFailureView({layout:current,texts:{}},cached,true).layout.anchors.context.x).toBe(62);
});
