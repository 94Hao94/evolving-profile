import type { TopologyNode, TopologyNodeData } from "./topology-spec";
import type { FlowReceipt } from "./flow-receipt";
import { inlineUiText } from "./inline-i18n";

export function topologySourceScope(events:Array<{source_type?:string;[key:string]:unknown}>,english:boolean,fallback:string){
  if(!events.length)return fallback;
  const host=events.filter(event=>event.source_type==='codex_host_tool_result').length;
  if(host===events.length)return english?'Same Prompt / retained host tool results (does not imply answer adoption)':'同一 Prompt / 宿主原始工具结果回放（不代表回答采用）';
  if(host)return english?'Same Prompt / mixed host results and EP invocation receipts (check delivery per item)':'同一 Prompt / 混合宿主结果与 EP 调用回执（逐条核对送达）';
  return english?'Same Prompt / EP invocation receipts (host delivery unverified)':'同一 Prompt / EP 调用回执（宿主送达尚未核验）';
}

export function summarizeReceiptScopes(receipts:FlowReceipt[]) {
  const unique=[...new Map(receipts.map((receipt,index)=>[`${receipt.session_id || ""}:${receipt.turn_id || ""}:${receipt.trace_id || index}`,receipt])).values()];
  const sum=(group:FlowReceipt[],field:"returned_count"|"delivered_count")=>group.every(receipt=>typeof receipt[field]==="number") ? group.reduce((total,receipt)=>total+(receipt[field] as number),0) : null;
  const group=(rows:FlowReceipt[])=>({calls:rows.length,returned:sum(rows,"returned_count"),delivered:sum(rows,"delivered_count")});
  const navigation=unique.filter(receipt=>typeof receipt.source_navigation_returned_count==="number");
  return {candidatePack:group(unique.filter(receipt=>["user_preference","get_preference"].includes(receipt.stage))),unitReadback:group(unique.filter(receipt=>["read_preference_unit","read_agent_process_memory"].includes(receipt.stage))),all:group(unique),sourceNavigationReturned:navigation.length ? navigation.reduce((sum,receipt)=>sum+(receipt.source_navigation_returned_count || 0),0) : null};
}

const processRecords = new Set(["observe-trajectory", "capability-observation", "failure-events", "repair-mode", "reusable-process-strategy", "migration-revalidation"]);
export function nodePurpose(id: string): "description" | "record" | "retrieval" {
  if (["prompt", "binding", "contract", "fork"].includes(id) || id.includes("guidance-") || id.endsWith("compatibility-gate")) return "description";
  if ([...processRecords].some(s=>id===`agent-process-memory-${s}`)) return "record";
  return "retrieval";
}
export function isContextBranch(id: string) {
  return nodePurpose(id)==="retrieval" || /agent-process-memory-guidance-(hint|recommend|scaffold|guard)$/.test(id);
}
export function nodeMetric(id: string, data: TopologyNodeData, english = false): string | null {
  const purpose=nodePurpose(id);
  if (purpose==="description") return null;
  if (purpose==="record") {
    if (!data.receipts.length) return null;
    const good=data.receipts.filter(r=>r.status!=="failed");
    const records=good.reduce((n,r)=>n+(r.returned_count ?? 0),0);
    const ev=good.flatMap(r=>r.verification_evidence || []);
    const tests=Math.max(0,...ev.filter(e=>e.status==="passed" || e.exit_code===0).map(e=>typeof e.tests==="number"?e.tests:0));
    if (id.endsWith("migration-revalidation")) return tests ? (english?`Validated ${tests} tests`:`验证 ${tests} 项 · 通过`) : (english?`Revalidations ${good.length}`:`再验证 ${good.length} 次`);
    return english?`Records ${records}`:`记录 ${records}`;
  }
  const known=data.receipts.length || data.counts.returned || data.counts.delivered || data.counts.candidates;
  if (!known) return null;
  if(data.status==="disabled") return english?"Disabled":"已禁用";
  const measured=data.receipts.some(r=>typeof r.candidate_count==="number");
  const candidate=measured || !data.receipts.length ? data.counts.candidates : "—";
  const navigation=summarizeReceiptScopes(data.receipts).sourceNavigationReturned;
  return `${english?"Candidates":"候选"} ${candidate ?? "—"} · ${english?"Delivered":"送达"} ${data.counts.delivered ?? "—"}${navigation===null ? "" : ` · ${inlineUiText("原文导航返回数", english ? "en" : undefined)} ${navigation}`}`;
}
export function contextChildren(nodes: TopologyNode[], lane: string, root: string, packet: string) {
  return nodes.filter(n=>n.data.lane===lane && n.id!==root && n.id!==packet && n.data.kind!=="lane" && isContextBranch(n.id));
}
