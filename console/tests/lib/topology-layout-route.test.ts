import { afterEach, expect, it, vi } from 'vitest';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { defaultTopologyLayout } from '@/lib/topology-layout';
let root:string|undefined;
afterEach(async()=>{vi.unstubAllEnvs();vi.resetModules();if(root)await rm(root,{recursive:true,force:true});root=undefined;});
async function route(){root=await mkdtemp(path.join(tmpdir(),'ep-layout-route-'));vi.stubEnv('EVOLVING_PROFILE_STATE_ROOT',root);vi.resetModules();return import('@/app/api/evolving-profile/topology-layout/route');}
const request=(origin:string,value:unknown)=>new Request(origin+'/api/evolving-profile/topology-layout',{method:'PUT',headers:{origin,'Content-Type':'application/json'},body:JSON.stringify(value)});
it('makes one saved layout readable by either loopback origin and rejects stale editors',async()=>{
  const {GET,PUT}=await route();const d=defaultTopologyLayout();d.anchors.context={x:62,y:8,width:15,height:8};
  expect((await PUT(request('http://localhost:9999',d))).status).toBe(200);
  const response=await GET();expect(response.headers.get('cache-control')).toBe('no-store');
  expect((await response.json()).anchors.context.x).toBe(62);
  expect((await PUT(request('http://127.0.0.1:9999',d))).status).toBe(409);
});
it('does not accept an external browser origin',async()=>{
  const {GET,PUT}=await route();const r=request('http://127.0.0.1:9999',defaultTopologyLayout());r.headers.set('origin','https://unrelated.example');
  expect((await PUT(r)).status).toBe(403);expect((await (await GET()).json()).revision).toBe(0);
});
it('accepts the browser authority when Next normalizes its internal request hostname',async()=>{
  const {GET,PUT}=await route();
  const normalized=new Request('http://localhost:9999/api/evolving-profile/topology-layout',{method:'PUT',headers:{host:'127.0.0.1:9999',origin:'http://127.0.0.1:9999','Content-Type':'application/json'},body:JSON.stringify(defaultTopologyLayout())});
  expect((await PUT(normalized)).status).toBe(200);
  expect((await (await GET()).json()).revision).toBe(1);
});
it('bounds incoming bytes and rejects incompatible canvas without creating a revision',async()=>{
  const {GET,PUT}=await route();
  expect((await PUT(request('http://localhost:9999',{padding:'x'.repeat(66000)}))).status).toBe(413);
  expect((await PUT(request('http://localhost:9999',{...defaultTopologyLayout(),canvas:{width:20,height:20,asset:'wrong'}}))).status).toBe(400);
  expect((await (await GET()).json()).revision).toBe(0);
});
