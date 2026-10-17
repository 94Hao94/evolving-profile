import {open,readFile,stat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {summarizeRuntimeLoad} from './runtime-load-evidence';

async function bounded(file:string,max:number) {
 const handle=await open(file,'r');try {const info=await handle.stat();if(info.size>max)throw new Error('read_limit');
  const bytes=Buffer.alloc(info.size);await handle.read(bytes,0,bytes.length,0);return bytes;
 }finally{await handle.close();}
}
async function digest(file:string){try{const raw=await bounded(file,2*1024*1024);return createHash('sha256').update(raw).digest('hex');}catch{return null;}}
async function tail(file:string){try{const handle=await open(file,'r');try{const info=await handle.stat(),start=Math.max(0,info.size-256*1024),bytes=Buffer.alloc(info.size-start);
 await handle.read(bytes,0,bytes.length,start);return bytes.toString('utf8').split('\n').slice(start?1:0).flatMap(line=>{try{return[JSON.parse(line)];}catch{return[];}});
 }finally{await handle.close();}}catch{return[];}}
export async function readRuntimeLoadEvidence(root:string,consoleRoot=process.cwd()){
 const config=path.join(root,'config/runtime-settings.json');
 const [saved,installed,events,modified,build,probe]=await Promise.all([
  digest(config),digest(path.join(root,'runtime/host-adapter/evolving_profile_controller_mcp.py')),
  tail(path.join(root,'audit/mcp-tool-activity.jsonl')),
  stat(config).then(s=>s.mtime.toISOString()).catch(()=>null),
  readFile(path.join(consoleRoot,'.next/BUILD_ID'),'utf8').then(s=>s.trim()).catch(()=>null),
  bounded(path.join(root,'audit/runtime-load-probe.json'),65536).then(b=>JSON.parse(b.toString())).catch(()=>null),
 ]);
 // A task-recorded actual native result is labeled separately from server
 // activity. It is a point-in-time probe, never proof of every connection.
 if(probe?.schema==='evolving-profile.actual-native-load-probe.v1' && probe.source==='actual_native_tool_result')events.push(probe);
 return summarizeRuntimeLoad({saved_config_sha256:saved,saved_config_at:modified,installed_mcp_sha256:installed,events,console_disk_build_id:build});
}
