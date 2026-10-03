import type { Edge, Node } from "@xyflow/react";
import type { FlowLane, FlowLaneSummary, FlowReceipt } from "@/lib/flow-receipt";

export type TopologyItem = { kind: string; text: string };
export type TopologyNodeData = {
  label: string;
  description: string;
  lane: FlowLane | "serial" | "writeback";
  kind: "stage" | "fork" | "merge" | "packet" | "tool" | "writeback" | "receipt" | "lane";
  status: string;
  counts: { candidates: number; returned: number; delivered: number; tokens: number };
  receipts: FlowReceipt[];
  items: TopologyItem[];
  sourceScope: string;
  english: boolean;
  width?: number;
  height?: number;
};
export type TopologyEdgeData = { kind: "serial" | "branch" | "merge" | "context" | "writeback"; status: string; points?: Array<{ x: number; y: number }> };
export type TopologyBranchSummary = {
  status: string;
  counts: { candidates: number; returned: number; delivered: number; tokens: number };
  receipts: FlowReceipt[];
  items: TopologyItem[];
};
export type TopologyNode = Node<TopologyNodeData>;
export type TopologyEdge = Edge<TopologyEdgeData>;

export function itemText(item: { text?: string; title?: string; id?: string }) { return item.text || item.title || item.id || "—"; }

export function buildTopologySpec(args: { english: boolean; summaries: Map<FlowLane, FlowLaneSummary>; sourceScope: string; userItems?: TopologyItem[]; guidanceItems?: TopologyItem[]; historyItems?: TopologyItem[]; branchSummaries?: Map<string, TopologyBranchSummary> }) {
  const { english, summaries, sourceScope } = args;
  const label = (en: string, zh: string) => english ? en : zh;
  const nodes: TopologyNode[] = [];
  const edges: TopologyEdge[] = [];
  const add = (id: string, data: Omit<TopologyNodeData, "english" | "sourceScope"> & Partial<Pick<TopologyNodeData, "english" | "sourceScope">>, extra: Partial<TopologyNode> = {}) => nodes.push({ id, type: data.kind, position: { x: 0, y: 0 }, data: { ...data, english, sourceScope }, ...extra });
  const edge = (id: string, source: string, target: string, kind: TopologyEdgeData["kind"] = "serial") => edges.push({ id, source, target, type: "orthogonal", data: { kind, status: "available" } });
  const zero = (lane: FlowLane | "serial" | "writeback") => summaries.get(lane as FlowLane) ?? { lane: lane as FlowLane, status: "not_observed", receipts: [], counts: { candidates: 0, returned: 0, delivered: 0, tokens: 0 } };
  const branch = (id: string, fallback: FlowLane): TopologyBranchSummary => args.branchSummaries?.get(id) ?? { status: "not_observed", counts: { candidates: 0, returned: 0, delivered: 0, tokens: 0 }, receipts: [], items: [] };
  const packet = (lane: FlowLane, name: string, zh: string, items: TopologyItem[] = []) => { const s = zero(lane); return { label: label(name, zh), description: label("Curated context packet", "整理后的上下文包"), lane, kind: "packet" as const, status: s.status, counts: s.counts, receipts: s.receipts, items, width: 188, height: 74 }; };
  add("prompt", { label: label("Prompt Ingress", "Prompt 入口"), description: label("User request received", "收到用户请求"), lane: "serial", kind: "stage", status: "observed", counts: zero("ingress").counts, receipts: zero("ingress").receipts, items: [], width: 170, height: 72 });
  add("binding", { label: label("Host / Hook Binding", "宿主 / Hook 绑定"), description: label("Bind tools, skills, environment", "绑定工具、Skill、环境"), lane: "serial", kind: "stage", status: "observed", counts: zero("ingress").counts, receipts: zero("ingress").receipts, items: [], width: 184, height: 72 });
  add("contract", { label: label("Task Contract", "任务契约"), description: label("Parse, plan, authorize", "解析、规划、授权"), lane: "serial", kind: "stage", status: "observed", counts: zero("guidance").counts, receipts: zero("guidance").receipts, items: [], width: 170, height: 72 });
  add("fork", { label: label("FORK", "分支"), description: label("Parallel lanes", "并行泳道"), lane: "serial", kind: "fork", status: "available", counts: { candidates: 0, returned: 0, delivered: 0, tokens: 0 }, receipts: [], items: [], width: 64, height: 64 });
  add("context", { label: label("Context Assembly", "上下文组装"), description: label("Unify memory and sources", "汇总记忆与来源"), lane: "serial", kind: "stage", status: zero("model_context").status, counts: zero("model_context").counts, receipts: zero("model_context").receipts, items: [], width: 184, height: 72 });
  add("execution", { label: label("Agent Execution", "Agent 执行"), description: label("Reason, act, generate", "推理、行动、生成"), lane: "serial", kind: "stage", status: zero("model_context").status, counts: zero("model_context").counts, receipts: zero("model_context").receipts, items: [], width: 174, height: 72 });
  edge("e-prompt-binding", "prompt", "binding"); edge("e-binding-contract", "binding", "contract"); edge("e-contract-fork", "contract", "fork"); edge("e-fork-context", "fork", "context", "context"); edge("e-context-execution", "context", "execution");

  const laneConfig: Array<{ lane: FlowLane; root: string; packetId: string; title: [string, string]; description: [string, string]; branches: Array<[string, string, string]> }> = [
    { lane: "user_memory", root: "user-root", packetId: "user-packet", title: ["User Memory", "用户记忆"], description: ["Preferences, history, long-term context", "偏好、历史、长期情境"], branches: [["User Preference", "用户偏好", "preference"], ["User Recall", "用户召回", "recall"], ["User Research", "用户研究", "research"], ["User Scenario Summary", "用户情景摘要", "scenario-summary"], ["User Source Readback", "用户原文回读", "read-source"]] },
    { lane: "agent_process", root: "agent-root", packetId: "agent-packet", title: ["Agent Memory", "智能体记忆"], description: ["Process retrieval, research, guidance", "过程召回、研究、指导"], branches: [["Agent Observe", "智能体观察", "observe-trajectory"], ["Agent Recall", "智能体召回", "process-retrieval"], ["Compatibility Gate", "兼容性门控", "compatibility-gate"], ["Agent Guidance", "智能体指导", "guidance"]] },
    { lane: "external_rag", root: "rag-root", packetId: "rag-packet", title: ["External RAG", "外部 RAG"], description: ["External documents and knowledge", "外部文档与知识"], branches: [["Lexical", "词法检索", "lexical"], ["Vector", "向量检索", "vector"], ["Fusion / RRF", "融合 / RRF", "fusion-rrf"], ["Rerank", "Rerank", "rerank"], ["JEV Review", "JEV 审查", "jev-review"]] },
  ];
  const userAggregateItems = [...(args.userItems ?? []), ...(args.guidanceItems ?? []), ...(args.historyItems ?? [])];
  for (const config of laneConfig) {
    const s = zero(config.lane); const root = config.root;
    const laneKey = config.lane === "agent_process" ? "agent-process-memory" : config.lane.replace("_", "-");
    const branchIds = config.branches.map(([, , stableKey]) => `${laneKey}-${stableKey}`);
    const childTotals = branchIds.map((id) => branch(id, config.lane));
    const aggregate = childTotals.reduce((acc, child) => ({ candidates: acc.candidates + child.counts.candidates, returned: acc.returned + child.counts.returned, delivered: acc.delivered + child.counts.delivered, tokens: acc.tokens + child.counts.tokens }), { candidates: 0, returned: 0, delivered: 0, tokens: 0 });
    const aggregateItems = childTotals.flatMap((child) => child.items);
    const hasBranchEvidence = childTotals.some((child) => child.receipts.length || child.items.length || child.counts.candidates || child.counts.returned || child.counts.delivered);
    const guidanceCounts = config.lane === "user_memory" ? { candidates: args.guidanceItems?.length ?? 0, returned: args.guidanceItems?.length ?? 0, delivered: args.guidanceItems?.length ?? 0, tokens: 0 } : { candidates: 0, returned: 0, delivered: 0, tokens: 0 };
    const rootCounts = { candidates: aggregate.candidates + guidanceCounts.candidates, returned: aggregate.returned + guidanceCounts.returned, delivered: aggregate.delivered + guidanceCounts.delivered, tokens: aggregate.tokens };
    add(root, { label: label(...config.title), description: label(...config.description), lane: config.lane, kind: "tool", status: hasBranchEvidence || guidanceCounts.returned ? (rootCounts.delivered ? "delivered" : rootCounts.returned ? "candidate_returned" : "observed") : s.status, counts: hasBranchEvidence || guidanceCounts.returned ? rootCounts : s.counts, receipts: childTotals.flatMap((child) => child.receipts), items: config.lane === "user_memory" ? [...aggregateItems, ...(args.guidanceItems ?? [])] : aggregateItems, width: 210, height: 86 });
    edge(`e-fork-${root}`, "fork", root, "branch");
    for (const [en, zh, stableKey] of config.branches) { const id = `${laneKey}-${stableKey}`; const projection = branch(id, config.lane); add(id, { label: label(en, zh), description: label("Route node", "路线节点"), lane: config.lane, kind: "tool", status: projection.status, counts: projection.counts, receipts: projection.receipts, items: projection.items, width: 150, height: 56 }); edge(`e-${root}-${id}`, root, id, "branch"); edge(`e-${id}-${config.packetId}`, id, config.packetId, "merge"); }
    add(config.packetId, packet(config.lane, config.lane === "external_rag" ? "RAG Packet" : config.lane === "agent_process" ? "Process Memory Packet" : "User Memory Packet", config.lane === "external_rag" ? "RAG 知识包" : config.lane === "agent_process" ? "过程记忆包" : "用户记忆包", config.lane === "user_memory" ? [...aggregateItems, ...(args.guidanceItems ?? [])] : aggregateItems));
    edge(`e-${config.packetId}-context`, config.packetId, "context", "context");
  }
  add("user-writeback", { label: label("User Writeback", "用户记忆写回"), description: label("Update user memory", "更新用户记忆"), lane: "writeback", kind: "writeback", status: zero("execution_writeback").status, counts: zero("execution_writeback").counts, receipts: zero("execution_writeback").receipts, items: [], width: 166, height: 66 });
  add("agent-writeback", { label: label("Agent Writeback", "智能体记忆写回"), description: label("Update process memory", "更新过程记忆"), lane: "writeback", kind: "writeback", status: zero("execution_writeback").status, counts: zero("execution_writeback").counts, receipts: zero("execution_writeback").receipts, items: [], width: 170, height: 66 });
  add("audit", { label: label("Audit Receipt", "审计回执"), description: label("Trace, citation, policy", "轨迹、引用、策略"), lane: "writeback", kind: "receipt", status: zero("execution_writeback").status, counts: zero("execution_writeback").counts, receipts: zero("execution_writeback").receipts, items: [], width: 160, height: 66 });
  add("response", { label: label("Final Response", "最终回答"), description: label("Deliver to user", "交付给用户"), lane: "writeback", kind: "writeback", status: zero("execution_writeback").status, counts: zero("execution_writeback").counts, receipts: zero("execution_writeback").receipts, items: [], width: 160, height: 66 });
  edge("e-execution-user-writeback", "execution", "user-writeback", "writeback"); edge("e-user-agent-writeback", "user-writeback", "agent-writeback", "writeback"); edge("e-agent-audit", "agent-writeback", "audit", "writeback"); edge("e-audit-response", "audit", "response", "writeback");
  return { nodes, edges };
}
