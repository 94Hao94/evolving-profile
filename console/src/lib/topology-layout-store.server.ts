import { copyFile, mkdir, open, readFile, rename, stat, unlink } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { defaultTopologyLayout, validateTopologyLayout, type TopologyLayout } from './topology-layout';

/** One installation owns one file; no hostname/port/locale-specific geometry. */
export async function readSharedLayout(file:string):Promise<TopologyLayout> {
  try {
    if((await stat(file)).size>65536)throw new Error('oversized');
    return validateTopologyLayout(JSON.parse(await readFile(file,'utf8')));
  } catch(error) {
    if((error as NodeJS.ErrnoException).code==='ENOENT')return defaultTopologyLayout();
    throw new Error('layout_unreadable');
  }
}

async function acquire(file:string) {
  const lock=file+'.lock';
  try {
    const handle=await open(lock,'wx',0o600);
    try {await handle.writeFile(JSON.stringify({pid:process.pid}));}
    catch(error){await handle.close();await unlink(lock);throw error;}
    return {handle,lock};
  }
  catch(error) {
    if((error as NodeJS.ErrnoException).code!=='EEXIST')throw error;
    // Do not break a lock based on age/PID: another process can acquire it
    // between inspection and unlink. Failure stays explicit and data is kept.
    throw new Error('layout_save_busy');
  }
}

export async function saveSharedLayout(file:string,input:unknown):Promise<TopologyLayout> {
  const draft=validateTopologyLayout(input);
  await mkdir(path.dirname(file),{recursive:true});
  const {handle,lock}=await acquire(file);const temporary=file+'.'+randomUUID()+'.tmp';
  try {
    const previous=await readSharedLayout(file);
    if(previous.revision!==draft.revision)throw new Error('layout_revision_conflict');
    const next={...draft,revision:previous.revision+1};
    // Backup before replacement; a failed write never destroys the last good file.
    if(previous.revision>0)await copyFile(file,file+'.previous');
    const output=await open(temporary,'wx',0o600);
    try {await output.writeFile(JSON.stringify(next,null,2)+'\n');await output.sync();}finally{await output.close();}
    await rename(temporary,file);
    return next;
  } finally {
    await unlink(temporary).catch(()=>{});
    await handle.close();await unlink(lock);
  }
}
