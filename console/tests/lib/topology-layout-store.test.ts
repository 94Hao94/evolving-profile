import { afterEach, expect, it } from 'vitest';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { defaultTopologyLayout } from '@/lib/topology-layout';
import { readSharedLayout, saveSharedLayout } from '@/lib/topology-layout-store.server';

const roots:string[]=[];
afterEach(async()=>{await Promise.all(roots.splice(0).map(root=>rm(root,{recursive:true,force:true})));});
async function location(){const root=await mkdtemp(path.join(tmpdir(),'ep-layout-test-'));roots.push(root);return path.join(root,'topology.json');}

it('persists custom coordinates and locale text for another page/client and keeps the old revision',async()=>{
  const file=await location();const draft=defaultTopologyLayout();
  draft.anchors.context={x:62,y:8,width:15,height:8};draft.texts.zh.context='我的上下文';
  const first=await saveSharedLayout(file,draft);expect(first.revision).toBe(1);
  const anotherClient=await readSharedLayout(file);expect(anotherClient.anchors.context).toEqual({x:62,y:8,width:15,height:8});
  expect(anotherClient.texts.en.context).toBeUndefined();expect(anotherClient.texts.zh.context).toBe('我的上下文');
  const second=await saveSharedLayout(file,{...anotherClient,anchors:{...anotherClient.anchors,context:{x:63,y:8,width:15,height:8}}});
  expect(second.revision).toBe(2);expect(JSON.parse(await readFile(file+'.previous','utf8')).anchors.context.x).toBe(62);
});

it('rejects a stale tab rather than overwriting newer shared coordinates',async()=>{
  const file=await location();const old=defaultTopologyLayout();await saveSharedLayout(file,old);
  await expect(saveSharedLayout(file,old)).rejects.toThrow('layout_revision_conflict');
  expect((await readSharedLayout(file)).revision).toBe(1);
});

it('has one successful writer for concurrent saves with the same revision',async()=>{
  const file=await location();const results=await Promise.allSettled([saveSharedLayout(file,defaultTopologyLayout()),saveSharedLayout(file,defaultTopologyLayout())]);
  expect(results.filter(r=>r.status==='fulfilled')).toHaveLength(1);
  expect(results.filter(r=>r.status==='rejected')).toHaveLength(1);
  expect((await readSharedLayout(file)).revision).toBe(1);
});

it('keeps corrupted or incompatible saved data intact and reports it, instead of silently resetting',async()=>{
  const file=await location();await writeFile(file,'broken');
  await expect(readSharedLayout(file)).rejects.toThrow('layout_unreadable');
  await expect(saveSharedLayout(file,defaultTopologyLayout())).rejects.toThrow('layout_unreadable');
  expect(await readFile(file,'utf8')).toBe('broken');
});

it('rejects an invalid anchor without changing the saved file',async()=>{
  const file=await location();const good=await saveSharedLayout(file,defaultTopologyLayout());const before=await readFile(file,'utf8');
  await expect(saveSharedLayout(file,{...good,anchors:{...good.anchors,context:{x:99,y:1,width:10,height:3}}})).rejects.toThrow('invalid_anchor');
  expect(await readFile(file,'utf8')).toBe(before);
});
