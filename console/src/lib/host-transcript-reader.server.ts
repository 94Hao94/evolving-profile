// Read-only native receipt lookup. Paths and source identity are checked before
// projection; a prepared packet is never promoted to host receipt evidence.
import { open, readdir, realpath, stat } from "node:fs/promises";
import path from "node:path";

const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TAIL_BYTES=8*1024*1024, MAX_LINE=32*1024*1024, MAX_BODY=32*1024*1024;
const MAX_SCAN=1024*1024*1024;
type Span={start:number;end:number|null;anchored:boolean;ino:number;dev:number};
type Scan={rows:any[];start:number|null;first:number|null;end:number|null;limited:boolean;bytes:number;resumeAt:number};

function inside(root:string,file:string) {
  const relative=path.relative(root,file);
  return relative!=="" && relative!==".." && !relative.startsWith(".."+path.sep) && !path.isAbsolute(relative);
}

async function scan(filename:string,start:number,end:number,session:string,turn:string):Promise<Scan> {
  const file=await open(filename,"r"),out:Scan={rows:[],start:null,first:null,end:null,limited:false,bytes:0,resumeAt:start};
  let buffer=Buffer.alloc(0),offset=start,bodyBytes=0,discard=false;
  try {
    if(start>0) {const previous=Buffer.alloc(1);await file.read(previous,0,1,start-1);discard=previous[0]!==10;}
    let position=start;
    while(position<end) {
      const chunk=Buffer.alloc(Math.min(128*1024,end-position));
      const {bytesRead}=await file.read(chunk,0,chunk.length,position);
      if(!bytesRead)break;position+=bytesRead;out.bytes+=bytesRead;
      buffer=Buffer.concat([buffer,chunk.subarray(0,bytesRead)]);
      let from=0,newline:number;
      while((newline=buffer.indexOf(10,from))>=0) {
        const length=newline-from+1,begin=offset+from;
        const line=buffer.subarray(from,newline);from=newline+1;
        if(discard) {discard=false;continue;}
        if(line.length>MAX_LINE) {out.limited=true;continue;}
        const text=line.toString("utf8").replace(/^\uFEFF/,"");
        if(!text.trim())continue;
        let row:any;try {row=JSON.parse(text);}catch {out.limited=true;continue;}
        const p=row?.payload,item=p?.item;
        if(row?.type!=="event_msg" || p?.turn_id!==turn || p.thread_id && p.thread_id!==session)continue;
        const boundary=["task_started","turn_started","task_complete","turn_end"].includes(p.type);
        const tool=item?.type==="McpToolCall" && item.server==="evolving_profile_controller";
        if(!boundary&&!tool)continue;
        if(bodyBytes+length>MAX_BODY) {out.limited=true;continue;}
        // Gaps preceding this turn are not gaps inside its source interval.
        if(out.first===null)out.limited=false;
        bodyBytes+=length;out.rows.push(row);out.first=out.first??begin;
        if(["task_started","turn_started"].includes(p.type))out.start=out.start??begin;
        if(["task_complete","turn_end"].includes(p.type)) {
          out.end=begin+length;
          if(out.start!==null) {out.resumeAt=out.end;return out;}
        }
      }
      buffer=Buffer.from(buffer.subarray(from));offset+=from;
      out.resumeAt=offset;
      if(buffer.length>MAX_LINE) {out.limited=true;offset+=buffer.length;buffer=Buffer.alloc(0);discard=true;}
      // The caller chose an exact turn; subsequent turns need not be scanned.
      if(out.start!==null&&out.end!==null)break;
    }
    return out;
  }finally {await file.close();}
}

export function createHostTranscriptReader(roots:string[]) {
  const spans=new Map<string,Span>();
  const missing=new Map<string,{size:number;mtime:number;ino:number;dev:number;cursor:number;limited:boolean}>();
  const pending=new Map<string,Promise<any>>();
  const locations=new Map<string,{at:number;file:string|null}>();
  async function locate(row:any) {
    const sid=row.session_id;
    const allowed=(await Promise.all(roots.map(root=>realpath(root).catch(()=>null)))).filter((r):r is string=>Boolean(r));
    const authorize=async(candidate:string)=>{
      const actual=await realpath(candidate).catch(()=>null);
      if(!actual||!allowed.some(root=>inside(root,actual))||!path.basename(actual).endsWith(`-${sid}.jsonl`))return null;
      return (await stat(actual)).isFile()?actual:null;
    };
    if(typeof row.transcript_path==="string" && row.transcript_path) {
      const actual=await realpath(row.transcript_path).catch(()=>null);
      // A caller-supplied out-of-root path must not redirect source lookup.
      if(actual&&!allowed.some(root=>inside(root,actual)))return null;
      const file=await authorize(row.transcript_path);if(file)return file;
    }
    const key=allowed.join("\0")+":"+sid,cached=locations.get(key);
    if(cached&&Date.now()-cached.at<30000&&!cached.file)return null;
    if(cached&&Date.now()-cached.at<30000&&cached.file) {
      const file=await authorize(cached.file);if(file)return file;
    }
    // Bounded metadata-only fallback, independent of the Prompt date. Do not
    // follow symlink directories or select arbitrarily between duplicate files.
    const queue=[...allowed],matches:string[]=[];let dirs=0,entries=0;
    while(queue.length&&dirs++<4096&&entries<50000) {
      const folder=queue.shift()!;
      for(const item of await readdir(folder,{withFileTypes:true}).catch(()=>[])) {
        if(++entries>50000)break;
        const candidate=path.join(folder,item.name);
        if(item.isDirectory())queue.push(candidate);
        else if(item.isFile()&&item.name.endsWith(`-${sid}.jsonl`)) {const file=await authorize(candidate);if(file)matches.push(file);}
      }
    }
    const file=!queue.length&&entries<=50000&&matches.length===1?matches[0]:null;
    if(locations.size>=100)locations.delete(locations.keys().next().value!);
    locations.set(key,{at:Date.now(),file});return file;
  }
  async function read(row:any) {
    if(!UUID.test(row?.session_id||"")||typeof row.turn_id!=="string"||!row.turn_id)return {status:"invalid_binding",rows:[],bytes:0};
    const filename=await locate(row);if(!filename)return {status:"source_unavailable",rows:[],bytes:0};
    const info=await stat(filename),file=await open(filename,"r");let meta:any,bytes=0;
    try {
      const head=Buffer.alloc(Math.min(info.size,128*1024));const {bytesRead}=await file.read(head,0,head.length,0);
      bytes+=bytesRead;
      const first=head.subarray(0,bytesRead).toString("utf8").replace(/^\uFEFF/,"").split("\n").find(line=>line.trim());
      try {meta=JSON.parse(first||"");}catch {return {status:"source_identity_unavailable",rows:[],bytes:bytesRead};}
    }finally {await file.close();}
    if(meta?.type!=="session_meta"||meta.payload?.id!==row.session_id)return {status:"source_identity_mismatch",rows:[],bytes:0};
    const key=filename+":"+row.turn_id,previous=spans.get(key);
    let result:Scan|undefined,strategy="tail_window";
    const noHit=missing.get(key);
    if(noHit&&noHit.ino===info.ino&&noHit.dev===info.dev) {
      if(noHit.size===info.size&&noHit.mtime===info.mtimeMs)
        return {status:noHit.limited?"read_budget_exceeded":"partial_source_read",rows:[meta],complete:false,bytes,strategy:"cached_missing_turn"};
      if(info.size>noHit.size) {
        result=await scan(filename,noHit.cursor,Math.min(info.size,noHit.cursor+MAX_SCAN),row.session_id,row.turn_id);
        bytes+=result.bytes;strategy="appended_source_lookup";
        if(info.size>noHit.cursor+MAX_SCAN)result.limited=true;
      }
    }
    if(!result&&previous&&previous.ino===info.ino&&previous.dev===info.dev&&(previous.end??previous.start)<=info.size) {
      result=await scan(filename,previous.start,Math.min(previous.end??info.size,previous.start+MAX_SCAN),row.session_id,row.turn_id);
      bytes+=result.bytes;
      if((previous.anchored?result.start===previous.start:result.first===previous.start)&&
         (previous.end===null||result.end===previous.end))strategy="cached_turn_range";
      else result=undefined;
    }
    if(!result) {
      const start=Math.max(0,info.size-TAIL_BYTES);
      result=await scan(filename,start,info.size,row.session_id,row.turn_id);
      bytes+=result.bytes;
      if(start>0&&result.rows.length&&(result.start===null||result.limited)) {
        strategy="expanded_tail_window";
        result=await scan(filename,Math.max(0,info.size-4*TAIL_BYTES),info.size,row.session_id,row.turn_id);
        bytes+=result.bytes;
      }
      if(start>0&&(result.start===null||result.limited)) {
        strategy="streamed_turn_lookup";
        result=await scan(filename,0,Math.min(info.size,MAX_SCAN),row.session_id,row.turn_id);
        bytes+=result.bytes;
        if(info.size>MAX_SCAN&&result.end===null)result.limited=true;
      }
    }
    const after=await stat(filename);
    if(after.ino!==info.ino||after.dev!==info.dev||after.size<info.size||after.size===info.size&&after.mtimeMs!==info.mtimeMs)
      return {status:"source_changed",rows:[],bytes,strategy};
    const complete=result.start!==null&&result.end!==null&&!result.limited;
    if(result.first!==null) {
      if(spans.size>=100)spans.delete(spans.keys().next().value!);
      spans.set(key,{start:result.start??result.first,end:result.end,anchored:result.start!==null,ino:info.ino,dev:info.dev});
      missing.delete(key);
    }else if(!result.rows.length) {
      if(missing.size>=100)missing.delete(missing.keys().next().value!);
      missing.set(key,{size:info.size,mtime:info.mtimeMs,ino:info.ino,dev:info.dev,cursor:result.resumeAt,limited:result.limited});
    }
    return {status:result.limited?"read_budget_exceeded":complete?"source_read":"partial_source_read",
      rows:[meta,...result.rows],complete,bytes,strategy};
  }
  return {read(row:any) {
    const key=JSON.stringify([row?.session_id,row?.turn_id,row?.transcript_path]);
    const active=pending.get(key);if(active)return active;
    const promise=read(row).finally(()=>pending.delete(key));pending.set(key,promise);return promise;
  }};
}
