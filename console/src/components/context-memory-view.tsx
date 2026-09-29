"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Calendar, List, Network, ScatterChart } from "lucide-react";
import { Constellation } from "./constellation";
import { Graph2D, type GraphData } from "./graph-2d";
import { describeManualSourceCoverage } from "@/lib/context-node";

type ContextNode = {
  id: string;
  type: string;
  label: string;
  identityStatus?: string;
  status?: string;
  reviewScope?: string;
  rawSourceCount?: number;
  sourceMessageCount?: number;
  manualSourceCoverage?: {
    scopeVerdict?: string;
    reviewedSourceMessageCount?: number;
    episodeScopeVerdict?: string;
  };
  summary?: Record<string, string>;
  summaryBudget?: Record<string, { truncated?: boolean; source_already_truncated?: boolean }>;
  sourceIds?: string[];
  projectKey?: string;
  sessionIds?: string[];
};

type ContextEdge = { source: string; target: string; type: string };
type ContextItem = { id: string; type: string; at?: string; label: string; status?: string };
type ContextPayload = {
  context?: {
    status?: string;
    sessionCount: number;
    projectCount: number;
    pendingReview?: number;
    qualityStatus?: string;
    graph?: {
      nodes: ContextNode[];
      edges: ContextEdge[];
      timeline: ContextItem[];
      bankRecordLinks: {
        available: boolean;
        linked: number;
        sampled?: number;
        scanned?: number;
        indexedAt?: string | null;
        sourceIndexUpdatedAt?: string | null;
        liveTotal?: number | null;
        unscanned?: number | null;
        coverage?: string;
        snapshotOnly?: boolean;
        reason: string;
      };
    };
  };
};

const shortId = (value: string) =>
  value
    .split(":")
    .map((part) => (part.length > 12 ? `…${part.slice(-8)}` : part))
    .join(":");
const relationName = (value: string) =>
  ({
    project_contains_session: "包含会话",
    workspace_contains_session: "同目录会话",
    project_contains_bank_record: "关联记录",
    workspace_links_bank_record: "同目录记录",
    session_supports_bank_record: "来源会话",
  })[value] ?? value;
const typeName = (type: string) =>
  type === "project"
    ? "已核实 Project"
    : type === "workspace"
      ? "工作目录线索"
      : type === "session"
        ? "Session 情境"
        : type === "bank_world"
          ? "Bank 事实"
          : type === "bank_experience"
            ? "Bank 经历"
            : "Bank 记录";

function ContextDetails({
  node,
  typeName,
}: {
  node: ContextNode;
  typeName: (value: string) => string;
}) {
  const [tier, setTier] = useState<"compact" | "standard" | "full">("compact");
  const summary = node.summary?.[tier] || "当前节点没有可显示的摘要。";
  const truncated = node.summaryBudget?.[tier]?.truncated || summary.endsWith("…");
  const unreviewed = node.status !== "model_reviewed";
  const scopeCoverage = describeManualSourceCoverage(node.manualSourceCoverage, node.sourceMessageCount);
  return (
    <div className="mt-4 space-y-4 text-xs">
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {(["compact", "standard", "full"] as const).map((value, index) => (
          <button
            key={value}
            onClick={() => setTier(value)}
            className={`flex-1 rounded-md px-2 py-1.5 ${tier === value ? "bg-background font-medium shadow-sm" : "text-muted-foreground"}`}
          >
            第 {index + 1} 层
          </button>
        ))}
      </div>
      {node.type === "workspace" && (
        <p className="text-amber-700">这只是相同工作目录的会话集合，不能据此认定为同一个项目。</p>
      )}
      {unreviewed && <p className="text-amber-700">确定性来源投影，尚未完成语义复核。</p>}
      {!unreviewed && node.reviewScope === "conversation_only_not_external_fact_verification" && (
        <p className="text-emerald-700">已按会话原文复核摘要；文件、发送和外部事实未在此核验。</p>
      )}
      <div className="rounded-lg border bg-muted/30 p-3">
        <div className="mb-2 text-[11px] text-muted-foreground">
          {typeName(node.type)} ·{" "}
          {tier === "compact" ? "概览" : tier === "standard" ? "标准摘要" : "详细摘要"}
          {truncated ? " · 已截断" : ""}
        </div>
        <p className="break-all whitespace-pre-wrap leading-5">{summary}</p>
      </div>
      <dl className="grid grid-cols-[80px_1fr] gap-y-2">
        <dt className="text-muted-foreground">节点名称</dt>
        <dd className="break-all">{node.label}</dd>
        {node.type === "session" ? (
          <>
            <dt className="text-muted-foreground">范围复核</dt>
            <dd className="break-words">{scopeCoverage ?? "未记录"}</dd>
          </>
        ) : null}
        <dt className="text-muted-foreground">来源数</dt>
        <dd>{node.sourceIds?.length ?? 0}</dd>
        <dt className="text-muted-foreground">来源定位</dt>
        <dd className="break-all font-mono text-[10px]">
          {(node.sourceIds ?? []).slice(0, 3).join("、") || "无"}
        </dd>
        <dt className="text-muted-foreground">边界</dt>
        <dd>来源定位是本机摘要路径，不是 Bank 的 read_source ID；关键事实仍需回到原始证据核验。</dd>
      </dl>
    </div>
  );
}

export function ContextMemoryView({ bankId }: { bankId: string | null }) {
  const [data, setData] = useState<ContextPayload | null>(null);
  const [viewMode, setViewMode] = useState<"constellation" | "graph" | "table" | "timeline">(
    "constellation"
  );
  const [selectedNode, setSelectedNode] = useState<ContextNode | null>(null);
  const detailsRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!bankId) return;
    fetch(`/api/evolving-profile/runtime?bankId=${encodeURIComponent(bankId)}`, {
      cache: "no-store",
    })
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null));
  }, [bankId]);
  const graph = data?.context?.graph;
  const edges = graph?.edges ?? [];
  const timeline = graph?.timeline ?? [];
  const visualData = useMemo<GraphData>(() => {
    const nodes = (graph?.nodes ?? []).slice(0, 240).map((node) => ({
      id: node.id,
      label: `${typeName(node.type)} · ${shortId(node.label)}`,
      group: node.type,
      color: node.type.startsWith("bank_")
        ? "#0ea5e9"
        : node.type === "project" || node.type === "workspace"
          ? "#8b5cf6"
          : "#22c55e",
      metadata: node,
    }));
    const ids = new Set(nodes.map((node) => node.id));
    return {
      nodes,
      links: edges
        .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
        .slice(0, 360)
        .map((edge) => ({
          source: edge.source,
          target: edge.target,
          type: edge.type,
          color: edge.type.includes("bank") ? "#38bdf8" : "#a78bfa",
        })),
    };
  }, [graph, edges]);
  const nodeColor = (node: any) =>
    node.group === "project" || node.group === "workspace"
      ? "#8b5cf6"
      : node.group === "session"
        ? "#22c55e"
        : "#0ea5e9";
  const linkColor = (link: any) => (link.type?.includes("bank") ? "#38bdf8" : "#a78bfa");
  const selectNode = (node: any) => {
    const source = (graph?.nodes ?? []).find((item) => item.id === node.id);
    const meta = node.metadata || source || {};
    setSelectedNode({
      id: node.id,
      type: source?.type || meta.type || node.group || node.type || "unknown",
      label: meta.label || node.label || node.id,
      identityStatus: meta.identityStatus,
      status: meta.status,
      reviewScope: meta.reviewScope,
      rawSourceCount: meta.rawSourceCount,
      sourceMessageCount: meta.sourceMessageCount,
      manualSourceCoverage: meta.manualSourceCoverage,
      summary: meta.summary,
      summaryBudget: meta.summaryBudget,
      sourceIds: meta.sourceIds,
      projectKey: meta.projectKey,
      sessionIds: meta.sessionIds,
    });
    if (window.matchMedia("(max-width: 1023px)").matches) {
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      requestAnimationFrame(() =>
        detailsRef.current?.scrollIntoView({
          behavior: reducedMotion ? "auto" : "smooth",
          block: "start",
        })
      );
    }
  };
  const button = (value: typeof viewMode, Icon: typeof ScatterChart, label: string) => (
    <button
      title={label}
      aria-label={label}
      onClick={() => setViewMode(value)}
      className={`inline-flex h-8 items-center justify-center gap-1 rounded-md px-2 text-xs font-medium sm:px-2.5 ${viewMode === value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
  if (data?.context?.status === "not_available_for_bank")
    return (
      <p className="py-8 text-sm text-muted-foreground">当前 Bank 尚未建立独立的情景摘要索引。</p>
    );
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-lg border p-4">
          <div className="text-xs text-muted-foreground">工作目录候选 · 非项目数</div>
          <div className="mt-1 text-2xl font-semibold">{data?.context?.projectCount ?? "—"}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs text-muted-foreground">Session Scenario Summary</div>
          <div className="mt-1 text-2xl font-semibold">{data?.context?.sessionCount ?? "—"}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs text-muted-foreground">图谱样本节点</div>
          <div className="mt-1 text-2xl font-semibold">{graph?.nodes.length ?? "—"}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs text-muted-foreground">Bank 已关联</div>
          <div className="mt-1 text-2xl font-semibold">{graph?.bankRecordLinks.linked ?? "—"}</div>
        </div>
      </div>
      <article className="rounded-lg border p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Network className="h-4 w-4 text-primary" />
              情景摘要可视化
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              与事实、经历、实体页使用同一套星座图、图谱、表格、时间线视图；点击节点可查看详情。
            </p>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
              <span className="rounded-full bg-violet-100 px-2 py-1 text-violet-800">
                紫：工作目录线索
              </span>
              <span className="rounded-full bg-green-100 px-2 py-1 text-green-800">
                绿：Session
              </span>
              <span className="rounded-full bg-sky-100 px-2 py-1 text-sky-800">蓝：Bank 记录</span>
            </div>
          </div>
          <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
            {button("constellation", ScatterChart, "星座")}
            {button("graph", Network, "图谱")}
            {button("table", List, "表格")}
            {button("timeline", Calendar, "时间线")}
          </div>
        </div>
        <div className="mt-4 flex min-w-0 flex-col gap-0 lg:flex-row">
          <div className="min-w-0 flex-1">
            {viewMode === "constellation" && (
              <Constellation
                data={visualData}
                height={620}
                nodeColorFn={nodeColor}
                nodeSizeFn={(node) => {
                  if (node.group === "project" || node.group === "workspace") return 7;
                  if (node.group === "session") return 5.5;
                  return 4.5;
                }}
                linkColorFn={linkColor}
                linkOpacity={0.18}
                linkWidth={0.7}
                onNodeClick={selectNode}
                preserveNodeColor
                compactLabels
                heatLegendLabel="关系"
              />
            )}
            {viewMode === "graph" && (
              <Graph2D
                data={visualData}
                height={620}
                showLabels
                onNodeClick={selectNode}
                nodeColorFn={nodeColor}
              />
            )}
            {viewMode === "table" && (
              <div className="max-h-[620px] overflow-auto rounded-lg border">
                <table className="w-full table-fixed text-xs">
                  <thead className="sticky top-0 bg-muted">
                    <tr>
                      <th className="p-2 text-left">来源节点</th>
                      <th className="p-2 text-left">关系</th>
                      <th className="p-2 text-left">目标节点</th>
                    </tr>
                  </thead>
                  <tbody>
                    {edges.slice(0, 500).map((edge) => (
                      <tr
                        key={`${edge.source}-${edge.target}`}
                        className="border-t hover:bg-muted/60"
                      >
                        <td className="break-all p-2 font-mono">
                          <button
                            type="button"
                            title="查看来源节点"
                            aria-label={`查看来源节点 ${shortId(edge.source)}`}
                            className="w-full text-left hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                            onClick={() =>
                              selectNode({
                                id: edge.source,
                                group: edge.source.split(":")[0],
                                label: edge.source,
                              })
                            }
                          >
                            {shortId(edge.source)}
                          </button>
                        </td>
                        <td className="p-2 text-muted-foreground">{relationName(edge.type)}</td>
                        <td className="break-all p-2 font-mono">
                          <button
                            type="button"
                            title="查看目标节点"
                            aria-label={`查看目标节点 ${shortId(edge.target)}`}
                            className="w-full text-left hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                            onClick={() =>
                              selectNode({
                                id: edge.target,
                                group: edge.target.split(":")[0],
                                label: edge.target,
                              })
                            }
                          >
                            {shortId(edge.target)}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {viewMode === "timeline" && (
              <div className="max-h-[620px] space-y-1 overflow-auto">
                {timeline
                  .slice()
                  .reverse()
                  .map((item) => (
                    <button
                      key={item.id}
                      onClick={() =>
                        selectNode({ id: item.id, group: item.type, label: item.label })
                      }
                      className="flex w-full items-center gap-2 rounded-md border border-transparent px-2 py-1.5 text-left text-xs hover:border-border"
                    >
                      <span className="w-24 shrink-0 rounded bg-muted px-1.5 py-1 text-center font-mono text-[10px] text-muted-foreground">
                        {item.at ? new Date(item.at).toLocaleDateString("zh-CN") : "未知时间"}
                      </span>
                      <span
                        className={`shrink-0 rounded px-1.5 py-1 text-[10px] ${item.type.startsWith("bank_") ? "bg-sky-100 text-sky-800" : "bg-violet-100 text-violet-800"}`}
                      >
                        {typeName(item.type)}
                      </span>
                      <span className="truncate" title={item.label}>
                        {shortId(item.label)}
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </div>
          <aside
            ref={detailsRef}
            className="mt-3 max-h-[620px] w-full min-w-0 overflow-y-auto border-t bg-card p-4 lg:mt-0 lg:w-80 lg:shrink-0 lg:border-l lg:border-t-0"
          >
            <div className="text-sm font-semibold">
              {selectedNode
                ? "情境摘要详情"
                : viewMode === "constellation"
                  ? "星座图说明"
                  : viewMode === "graph"
                    ? "图谱说明"
                    : viewMode === "table"
                      ? "关系表说明"
                      : "时间线说明"}
            </div>
            {selectedNode ? (
              <ContextDetails node={selectedNode} typeName={typeName} />
            ) : (
              <div className="mt-4 space-y-3 text-xs leading-5 text-muted-foreground">
                <p>点击图谱节点、表格中的来源或目标节点、时间线项目，详情显示在此处。</p>
                <p>紫色是 Project，绿色是 Session，蓝色是 Bank 事实/经历/记录。</p>
                <p>
                  当前图谱展示 {visualData.nodes.length} 个样本节点，共{" "}
                  {graph?.bankRecordLinks.linked ?? 0} 条 Bank 关联。
                </p>
              </div>
            )}
          </aside>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Bank 关联快照：
          {graph?.bankRecordLinks.available
            ? `${graph.bankRecordLinks.linked} / ${graph.bankRecordLinks.scanned ?? "未知"} 条扫描记录（页面样本 ${graph.bankRecordLinks.sampled ?? 0} 条）`
            : "尚无可用关联快照"}
          。当前 Bank 共 {graph?.bankRecordLinks.liveTotal ?? "未知"} 条，快照后新增{" "}
          {graph?.bankRecordLinks.unscanned ?? "未知"} 条未扫描；快照时间{" "}
          {graph?.bankRecordLinks.indexedAt
            ? new Date(graph.bankRecordLinks.indexedAt).toLocaleString("zh-CN")
            : "未知"}
          ；情景摘要待复核 {data?.context?.pendingReview ?? "未知"} 条。
        </p>
      </article>
    </div>
  );
}
