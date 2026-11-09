import { epStatePath, EP_HOST_SESSIONS } from "@/lib/ep-state-paths";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { projectHostTurnReplay } from "./host-tool-replay";
import { mergeToolReceipts } from "./tool-receipt";
import { createHostTranscriptReader } from "./host-transcript-reader.server";
const root=EP_HOST_SESSIONS;
const ingressPath=epStatePath("audit/prompt-ingress.jsonl");
const archived=process.env.EVOLVING_PROFILE_HOST_ARCHIVED_SESSIONS_ROOT || path.join(path.dirname(root),"archived_sessions");
const reader=createHostTranscriptReader([root,archived]);
export async function readReplayPrompts():Promise<any[]> {
  try {return JSON.parse(await readFile(epStatePath("audit/host-replay-prompts.json"),"utf8"));}
  catch{return [];}
}
export async function enrichHostToolReceipt(promptId:string,detail:any) {
  try {
    const ingress=(await readFile(ingressPath,"utf8")).trim().split("\n").flatMap(l=>{try{return [JSON.parse(l)]}catch{return []}});
    // The full timestamp is part of identity: repeated identical Prompts must not steal each other's calls.
    const row=[...ingress,...await readReplayPrompts()].findLast((r:any)=>`${r.prompt_fingerprint}:${r.at}`===promptId);
    if(!row?.session_id || !row.turn_id || !/^[-0-9a-f]{36}$/.test(row.session_id)) return detail;
    const read=await reader.read(row);
    if(!read.rows.length)return {...detail,host_replay_read:{status:read.status,bytes_read:read.bytes}};
    const projected=projectHostTurnReplay(read.rows,{session_id:row.session_id,turn_id:row.turn_id});
    const coverage=read.complete?projected.call_coverage:"partial";
    const complete=coverage==="exact_host_turn_complete";
    const events=mergeToolReceipts(detail?.memory_route_receipt?.tool_events || [],projected.tool_events,{hostTurnComplete:complete});
    return {...detail,session_id:row.session_id,turn_id:row.turn_id,
      host_replay_read:{status:read.status,bytes_read:read.bytes,strategy:read.strategy},
      memory_route_receipt:{...detail?.memory_route_receipt,tool_events:events,
        call_coverage:coverage,
        receipt_source:"codex_host_tool_result",returned_count:complete && events.every(event=>typeof event.returned_count==="number") ? events.reduce((s,e)=>s+e.returned_count,0) : null,
        audit_boundary:"exact_session_turn_host_replay_not_original_ep_ledger",
        original_ep_events:detail?.memory_route_receipt?.tool_events || []},
      audit_source_scope:"prompt_bound_host_result_replay"};
  }catch{return detail;}
}
