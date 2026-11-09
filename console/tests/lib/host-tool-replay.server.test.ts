import { afterEach, expect, it, vi } from "vitest";
import { mkdtemp, mkdir, writeFile, appendFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

const sid="11111111-1111-4111-8111-111111111111";
const turn="turn-a";
const at="2026-10-18T10:00:00Z";
const roots:string[]=[];
afterEach(async()=>{vi.unstubAllEnvs();vi.resetModules();await Promise.all(roots.splice(0).map(p=>rm(p,{recursive:true,force:true})));});
function rows(session=sid, id=turn, body="actual preference") {
  return [{type:"session_meta",payload:{id:session}},
    {type:"event_msg",payload:{type:"task_started",thread_id:session,turn_id:id}},
    {type:"event_msg",payload:{type:"item_completed",thread_id:session,turn_id:id,item:{
      type:"McpToolCall",id:"native-call",server:"evolving_profile_controller",tool:"user_preference",status:"completed",
      arguments:{check_id:"test-check"},result:{content:[{type:"text",text:JSON.stringify({
        tool_call_id:"mcp:real",returned_count:1,included:[{id:"pref",text:body}]})}]}}}},
    {type:"event_msg",payload:{type:"task_complete",thread_id:session,turn_id:id}}];
}
const encode=(r:any[])=>r.map(v=>JSON.stringify(v)+"\n").join("");
async function fixture({foreign=false,archived=false,declared=true}={}) {
  const dir=await mkdtemp(path.join(tmpdir(),"ep-replay-"));roots.push(dir);
  const state=path.join(dir,"state"),sessions=path.join(dir,"sessions"),archive=path.join(dir,"archived_sessions");
  const folder=path.join(archived?archive:sessions,"2026","10","01");
  await mkdir(folder,{recursive:true});await mkdir(path.join(state,"audit"),{recursive:true});
  const file=path.join(folder,`rollout-2026-10-01T00-00-00-${sid}.jsonl`);
  await writeFile(file,encode(rows(foreign?"22222222-2222-4222-8222-222222222222":sid)));
  await writeFile(path.join(state,"audit","prompt-ingress.jsonl"),encode([{prompt_fingerprint:"fp",at,session_id:sid,turn_id:turn,...(declared?{transcript_path:file}:{})}]));
  vi.stubEnv("EVOLVING_PROFILE_STATE_ROOT",state);vi.stubEnv("EVOLVING_PROFILE_HOST_SESSIONS_ROOT",sessions);
  vi.stubEnv("EVOLVING_PROFILE_HOST_ARCHIVED_SESSIONS_ROOT",archive);vi.resetModules();
  const {enrichHostToolReceipt}=await import("@/lib/host-tool-replay.server");
  const read=()=>enrichHostToolReceipt(`fp:${at}`,{prompt_id:`fp:${at}`,memory_route_receipt:{tool_events:[]}});
  return {read,file,state,sessions,archive};
}

it("recovers a cross-date old-session tool return using the recorded path",async()=>{
  const {read}=await fixture();const result=await read();
  expect(result.memory_route_receipt.tool_events).toMatchObject([{tool:"user_preference",returned_count:1,delivered_count:1}]);
  expect(result.memory_route_receipt.call_coverage).toBe("exact_host_turn_complete");
});
it("finds old and archived native sessions when the path is absent",async()=>{
  for(const archived of [false,true]) {
    const {read}=await fixture({archived,declared:false});
    expect((await read()).memory_route_receipt.tool_events[0]?.delivered_count).toBe(1);
  }
});
it("rejects a declared file whose native session identity belongs to another session",async()=>{
  const {read}=await fixture({foreign:true});
  expect((await read()).memory_route_receipt.tool_events).toEqual([]);
});
it("does not read a declared file outside the configured source roots",async()=>{
  const f=await fixture();const outside=path.join(path.dirname(f.state),"outside.jsonl");
  await writeFile(outside,encode(rows()));
  await writeFile(path.join(f.state,"audit","prompt-ingress.jsonl"),encode([{prompt_fingerprint:"fp",at,session_id:sid,turn_id:turn,transcript_path:outside}]));
  const result=await f.read();
  expect(result.memory_route_receipt.tool_events).toEqual([]);
});
it("uses cached turn ranges after another turn is appended without losing source evidence",async()=>{
  const {read,file}=await fixture();await read();
  await appendFile(file,encode(rows(sid,"other-turn","not this prompt").slice(1)));
  const result=await read();
  expect(result.memory_route_receipt.tool_events[0]?.mapping_items[0].text).toBe("actual preference");
  expect(result.host_replay_read?.strategy).toBe("cached_turn_range");
});
it("keeps repeated identical prompts isolated by occurrence and turn",async()=>{
  const {read,file,state}=await fixture();await appendFile(file,encode(rows(sid,"turn-b","different prompt body").slice(1)));
  await appendFile(path.join(state,"audit","prompt-ingress.jsonl"),encode([{prompt_fingerprint:"fp",at:"2026-10-19T10:00:00Z",session_id:sid,turn_id:"turn-b",transcript_path:file}]));
  expect((await read()).memory_route_receipt.tool_events[0]?.mapping_items[0].text).toBe("actual preference");
});
it("does not rescan a large unchanged running turn on every refresh",async()=>{
  const {read,file}=await fixture();
  const padding=JSON.stringify({type:"ignored",text:"x".repeat(1024*1024)})+"\n";
  await writeFile(file,encode(rows().slice(0,1))+padding.repeat(16)+encode(rows().slice(1,-1)));
  await read();const second=await read();
  expect(second.memory_route_receipt.tool_events[0]?.delivered_count).toBe(1);
  expect(second.host_replay_read.bytes_read).toBeLessThan(1024*1024);
  await appendFile(file,encode(rows().slice(-1)));
  expect((await read()).memory_route_receipt.call_coverage).toBe("exact_host_turn_complete");
});
it("caches an unchanged missing turn and notices appended source events",async()=>{
  const {read,file}=await fixture();
  const padding=JSON.stringify({type:"ignored",text:"x".repeat(1024*1024)})+"\n";
  await writeFile(file,encode(rows().slice(0,1))+padding.repeat(16));
  await read();const second=await read();
  expect(second.memory_route_receipt.tool_events).toEqual([]);
  expect(second.host_replay_read.bytes_read).toBeLessThan(1024*1024);
  await appendFile(file,encode(rows().slice(1)));
  expect((await read()).memory_route_receipt.tool_events[0]?.delivered_count).toBe(1);
});
it("does not let unrelated old malformed rows prevent a valid turn from being cached",async()=>{
  const {read,file}=await fixture();
  const padding=JSON.stringify({type:"ignored",text:"x".repeat(1024*1024)})+"\n";
  await writeFile(file,encode(rows().slice(0,1))+"unrelated historical malformed row\n"+encode(rows().slice(1))+padding.repeat(10));
  const first=await read();
  expect(first.memory_route_receipt.call_coverage).toBe("exact_host_turn_complete");
  expect((await read()).host_replay_read.strategy).toBe("cached_turn_range");
});
it("keeps a malformed row inside the selected turn partial rather than dropping source gaps",async()=>{
  const {read,file}=await fixture();const r=rows();
  await writeFile(file,encode(r.slice(0,2))+"malformed inside turn\n"+encode(r.slice(2)));
  expect((await read()).memory_route_receipt.call_coverage).toBe("partial");
  expect((await read()).host_replay_read.strategy).toBe("cached_turn_range");
});
it("preserves a valid large compaction record inside the turn without losing its receipts",async()=>{
  const {read,file}=await fixture();const r=rows();
  const compacted=JSON.stringify({type:"compacted",payload:{summary:"x".repeat(9*1024*1024)}})+"\n";
  await writeFile(file,encode(r.slice(0,2))+compacted+encode(r.slice(2)));
  expect((await read()).memory_route_receipt.call_coverage).toBe("exact_host_turn_complete");
  expect((await read()).host_replay_read.strategy).toBe("cached_turn_range");
});
