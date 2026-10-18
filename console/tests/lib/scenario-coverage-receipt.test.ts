import { expect, it } from "vitest";
import { normalizeToolResult } from "@/lib/tool-receipt";
import { projectHostToolRows } from "@/lib/host-tool-replay";
import { projectToolBranches } from "@/lib/topology-mapping";

const common = {source:"scenario_coverage_ledger",scenario_id:"session:source",snapshot_id:"snapshot",
  status:"global_pending",semantic_review_status:"not_reviewed",requirement_count:41,
  source_readback:false,has_unread_requirements:true,returned_count:0};

it("projects the actual coverage page despite the old MCP zero-count bug without inventing 41 returns",()=>{
  const body={...common,view:"requirements",requirements:[{requirement_id:"req-1",text:"不要覆盖原文件",status:"unresolved",source_locator:{raw_line_sha256:"line"}}]};
  const normalized=normalizeToolResult("read_scenario_summary",body);
  expect(normalized).toMatchObject({returned_count:1,reported_returned_count:0,return_count_basis:"coverage_returned_body",
    memory_ids:[],scenario_ids:["session:source"],original_message_readback_count:0,
    scenario_coverage_view:"requirements",scenario_semantic_review_status:"not_reviewed"});
  expect(normalized.mapping_items[0]).toMatchObject({id:"req-1",text:"不要覆盖原文件",source_role:"scenario_requirement"});
  expect(body.returned_count).toBe(0);
});

it("projects original source text and separate readback evidence from a real host row",()=>{
  const body={...common,view:"source",source_readback:true,raw_source_status:"source_read",
    raw_source:{text:"原始消息，不是摘要",locators:[{raw_line_sha256:"line"}]}};
  const row={type:"event_msg",payload:{type:"item_completed",thread_id:"host",turn_id:"turn",
    item:{type:"McpToolCall",id:"call",server:"evolving_profile_controller",tool:"read_scenario_summary",status:"completed",
      arguments:{purpose:"agent_process"},result:{content:[{type:"text",text:JSON.stringify(body)}]}}}};
  const event=projectHostToolRows([row],{session_id:"host",turn_id:"turn"})[0];
  expect(event).toMatchObject({returned_count:1,reported_returned_count:0,delivered_count:1,original_message_readback_count:1,
    scenario_coverage_view:"source",scenario_ids:["session:source"],memory_ids:[],
    delivery:{host_visibility:"observed",answer_use:"not_measured"}});
  expect(event.mapping_items[0]).toMatchObject({text:"原始消息，不是摘要",source_role:"original_source"});
});

it("keeps actual relation edges visible and never invents original reads",()=>{
  const relation={type:"supersedes",from:"a",to:"b",evidence_quote:"改为新值"};
  const out=normalizeToolResult("read_scenario_summary",{...common,view:"relations",relations:[relation]});
  expect(out.returned_count).toBe(1);
  expect(out.mapping_items[0].source_role).toBe("scenario_relation");
  expect(JSON.parse(out.mapping_items[0].text)).toEqual(relation);
  expect(out.original_message_readback_count).toBe(0);
});

it("keeps overview, empty, denied and failed coverage separate from body delivery",()=>{
  for(const body of [
    {...common,view:"overview"}, {...common,view:"requirements",requirements:[]},
    {...common,view:"source",raw_source_status:"source_unavailable",raw_source:{text:"not a read"}},
    {...common,view:"requirements",permission_status:"denied",requirements:[{requirement_id:"r",text:"blocked"}]},
  ]) {
    const out=normalizeToolResult("read_scenario_summary",body);
    expect(out.returned_count).toBe(0);expect(out.mapping_items).toEqual([]);expect(out.original_message_readback_count).toBe(0);
  }
  const failed=normalizeToolResult("read_scenario_summary",{...common,view:"requirements",requirements:[{requirement_id:"r",text:"failed"}]},true);
  expect(failed.returned_count).toBe(0);expect(failed.mapping_items).toEqual([]);
});

it("shows coverage view, semantic state and original readback in Chinese and English details",()=>{
  const event={tool:"read_scenario_summary",tool_call_id:"call",purpose:"navigation",returned_count:1,
    scenario_ids:["session:source"],scenario_coverage_view:"source",scenario_summary_status:"global_pending",
    scenario_semantic_review_status:"not_reviewed",original_message_readback_count:1};
  const zh=projectToolBranches([event],false).get("user-memory-scenario-summary")!;
  const en=projectToolBranches([event],true).get("user-memory-scenario-summary")!;
  const zhText=zh.items.map(i=>i.text).join("\n"),enText=en.items.map(i=>i.text).join("\n");
  expect(zhText).toContain("原始消息回读 1");expect(zhText).toContain("全局审查待完成");
  expect(zhText).not.toContain("global_pending");expect(zhText).not.toContain("not_reviewed");
  expect(enText).toContain("Original messages read 1");expect(enText).not.toMatch(/[\u3400-\u9fff]/u);
});
