import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { NextIntlClientProvider } from "next-intl";
import { expect,it } from "vitest";
import en from "@/messages/en.json";
import { ExecutionTopologyCanvas } from "@/components/execution-topology-canvas";
import { projectFlowAudit } from "@/lib/flow-projection";
import { nodeMetric,contextChildren } from "@/lib/topology-presentation";
import { buildTopologySpec } from "@/lib/topology-spec";
it("does not let an unused planned branch erase an observed host-received subtotal",()=>{
 const branches=new Map<string,any>([
  ["user-memory-preference",{status:"delivered",counts:{candidates:null,returned:5,delivered:5,tokens:0},receipts:[{trace_id:"p",returned_count:5,delivered_count:5}],items:[]}],
  ["user-memory-recall",{status:"observed",counts:{candidates:0,returned:0,delivered:null,tokens:0},receipts:[],items:[]}]
 ]);
 const nodes=buildTopologySpec({english:false,summaries:new Map(),sourceScope:"test",branchSummaries:branches}).nodes;
 expect(nodes.find(n=>n.id==="user-root")?.data.counts.delivered).toBe(5);
 expect(contextChildren(nodes,"user_memory","user-root","user-packet").map(n=>n.id)).toEqual(["user-memory-preference"]);
});
it.each([true,false])("keeps prepared provenance through every aggregate, including mixed receipts (%s)",english=>{
 for(const mixed of [false,true]) {
  const branches=new Map<string,any>([["user-memory-preference",{preparedCount:8,status:"candidate_returned",counts:{candidates:4,returned:8,delivered:null,tokens:0},receipts:[],items:[{kind:"Preference",text:"prepared"}]}]]);
  if(mixed)branches.set("user-memory-recall",{status:"delivered",counts:{candidates:3,returned:2,delivered:2,tokens:0},receipts:[{trace_id:"actual",stage:"user_recall",returned_count:2,delivered_count:2}],items:[]});
  const nodes=buildTopologySpec({english,summaries:new Map(),sourceScope:"test",branchSummaries:branches}).nodes;
  for(const id of ["user-root","user-packet","context","execution"]) {
   const metric=nodeMetric(id,nodes.find(n=>n.id===id)!.data,english)!;
   expect(metric).toContain(english?"Prepared 8":"已准备 8");
   expect(metric).not.toContain(english?"Returned 10":"返回 10");
   if(mixed)expect(metric).toContain(english?"Returned 2":"返回 2");
  }
 }
});
it.each([true,false])("distinguishes returned content from unconfirmed host delivery (%s)",english=>{
 const metric=nodeMetric("user-memory-recall",{counts:{candidates:7,returned:4,delivered:null},receipts:[{candidate_count:7}],status:"candidate_returned"} as any,english)!;
 expect(metric).toContain(english?"Returned 4":"返回 4");
 expect(metric).toContain(english?"unconfirmed":"未确认");
 expect(metric).not.toContain(english?"Delivered 0":"送达 0");
});
it("labels Hook-only preference bodies as prepared, not confirmed returns",()=>{
 const metric=nodeMetric("user-memory-preference",{counts:{candidates:4,returned:8,delivered:null},receipts:[],status:"candidate_returned"} as any,false)!;
 expect(metric).toContain("已准备 8");expect(metric).toContain("未确认");
});
it.each([true,false])("does not call prepared Hook preference delivered (audit=%s)",audit=>{
 const prompt={prompt_id:"p",at:"a",user_prompt:"x",guidance_receipt:{host_state:"hook_context_prepared",guidance_items:[{id:"pref",text:"prepared only"}]}};
 const markup=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale:"en",messages:en,timeZone:"Asia/Shanghai",children:createElement(ExecutionTopologyCanvas,{promptId:"p",english:true,audit:audit?projectFlowAudit(prompt):undefined,guidanceReceipt:prompt.guidance_receipt})}));
 expect(markup).not.toContain("Delivered 1");expect(markup).toContain("Delivered —");
});
it("does not call unknown delivery zero for legacy historical audit",()=>{
 const prompt={prompt_id:"p",at:"a",user_prompt:"x",historical_audit:{route:"recall",state:"observed",candidate_count:2,returned_to_host_count:1,delivery_state:"not_measured"}};
 const markup=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale:"en",messages:en,timeZone:"Asia/Shanghai",children:createElement(ExecutionTopologyCanvas,{promptId:"p",english:true,audit:projectFlowAudit(prompt as any)})}));
 expect(markup).not.toContain("Candidates 2 · Delivered 0");
});
