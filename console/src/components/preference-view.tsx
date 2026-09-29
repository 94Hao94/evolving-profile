"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale } from "next-intl";
import { Constellation } from "@/components/constellation";
import { Graph2D, type GraphNode } from "@/components/graph-2d";
import {
  buildPreferenceGraph,
  preferenceDimensionColor,
  preferenceDimensionLabel,
  FUSION_MODEL_COLOR,
  type FusionModel,
  type PreferenceDimension,
  type PreferenceLocale,
  type PreferenceUnit,
} from "@/lib/preference-graph";
import {
  preferenceTableRows,
  preferenceTimelineEvents,
  visiblePreferenceUnits,
  type PreferenceSelection,
  type PreferenceLifecycle,
  type PreferenceTableRow,
} from "@/lib/preference-view-model";

const DIMENSIONS: PreferenceDimension[] = [
  "communication",
  "learning",
  "reasoning",
  "collaboration",
  "delivery",
];

type Selection = PreferenceSelection;
type ViewMode = "constellation" | "graph" | "table" | "timeline";

const FUSION_COLOR = FUSION_MODEL_COLOR;

const COPY = {
  zh: {
    title: "多维度偏好", intro: "当前 Prompt 优先。以下内容只在适用范围内作为参考，不自动扩张为执行授权。",
    approved: "已审核", pending: "待审核", superseded: "已失效", allRecords: "全部记录", all: "全部显示",
    fusion: "融合心智模型", scope: "显示范围：", constellation: "星座图", graph: "图谱", table: "表格", timeline: "时间线",
    loading: "正在读取多维度偏好…", unavailable: "多维度偏好注册表暂时不可读取。", kind: "类型", content: "内容", status: "状态", time: "时间",
    active: "正式可用", noRows: "当前筛选没有可显示的条目。", noTimeline: "当前筛选没有可显示的时间事件。",
    colors: "颜色与数量", currentView: "当前视图：", details: "节点详情", detailHint: "点击星座中的偏好或心智模型节点查看适用范围、机制和来源引用。",
    applies: "适用：", exceptions: "例外：", action: "行动影响：", evidence: "证据", model: "融合心智模型",
    noMechanism: "该模型尚未登记机制正文。", dynamicFusion: "融合心智模型不是固定五个领域，而是随着多维度偏好证据持续新增、修订、合并与归档的动态机制集合。",
    pendingExplanation: "待审核条目保留用于核对和后续加工，当前不会进入 Agent 的多维度偏好指导包。它们通常还缺少独立原文证据、适用范围确认，或需要先处理与现有条目的重复和冲突。",
    supersededExplanation: "已失效条目保留历史来源，但不会作为当前指导返回给 Agent。",
  },
  en: {
    title: "Multi-dimensional Preferences", intro: "The current prompt takes priority. These entries are conditional references and do not extend execution authority.",
    approved: "Reviewed", pending: "Pending review", superseded: "Superseded", allRecords: "All records", all: "All",
    fusion: "Fused mental models", scope: "Display:", constellation: "Constellation", graph: "Graph", table: "Table", timeline: "Timeline",
    loading: "Loading preferences...", unavailable: "The preference registry is temporarily unavailable.", kind: "Type", content: "Content", status: "Status", time: "Time",
    active: "Active", noRows: "No entries match the current filter.", noTimeline: "No timeline events match the current filter.",
    colors: "Colors and counts", currentView: "Current view:", details: "Details", detailHint: "Select a preference or mental-model node to inspect scope, mechanism, and sources.",
    applies: "Applies:", exceptions: "Exceptions:", action: "Action impact:", evidence: "evidence", model: "Fused mental model",
    noMechanism: "No mechanism body is registered for this model.", dynamicFusion: "Fused mental models are a dynamic set of mechanisms. They are not a fixed set of five domains.",
    pendingExplanation: "Pending entries are retained for review and follow-up processing. They are not included in the Agent's current preference packet because evidence, scope, duplication, or conflicts still need review.",
    supersededExplanation: "Superseded entries retain their historical sources but are not returned as current Agent guidance.",
  },
} as const;

export function PreferenceView() {
  const locale = useLocale();
  const language: PreferenceLocale = locale.startsWith("zh") ? "zh" : "en";
  const copy = COPY[language];
  const [units, setUnits] = useState<PreferenceUnit[]>([]);
  const [models, setModels] = useState<FusionModel[]>([]);
  const [selection, setSelection] = useState<Selection>("all");
  const [lifecycle, setLifecycle] = useState<PreferenceLifecycle>("approved");
  const [viewMode, setViewMode] = useState<ViewMode>("constellation");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch("/api/evolving-profile/guidance/units?limit=500&cursor=0", {
        signal: controller.signal,
        cache: "no-store",
      }).then((response) => response.json()),
      fetch("/api/evolving-profile/guidance/models", {
        signal: controller.signal,
        cache: "no-store",
      }).then((response) => response.json()),
    ])
      .then(([unitResponse, modelResponse]) => {
        setUnits(unitResponse.items ?? []);
        setModels(modelResponse.items ?? []);
      })
      .catch((cause) => {
        if (cause.name !== "AbortError") setError(copy.unavailable);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const filteredUnits = useMemo(() => visiblePreferenceUnits(units, selection, lifecycle), [lifecycle, selection, units]);
  const visibleAllUnits = useMemo(() => visiblePreferenceUnits(units, "all", lifecycle), [lifecycle, units]);
  const visibleModelCount = lifecycle === "needs_review" || lifecycle === "superseded" ? 0 : models.length;
  const graph = useMemo(() => buildPreferenceGraph(filteredUnits, models, selection, language), [filteredUnits, language, models, selection]);
  const tableRows = useMemo(() => preferenceTableRows(units, models, selection, lifecycle), [lifecycle, models, selection, units]);
  const timelineEvents = useMemo(() => preferenceTimelineEvents(units, models, selection, lifecycle), [lifecycle, models, selection, units]);
  const countByDimension = useMemo(
    () =>
      Object.fromEntries(
        DIMENSIONS.map((dimension) => [
          dimension,
          visibleAllUnits.filter((unit) => unit.primary_category === dimension).length,
        ])
      ) as Record<PreferenceDimension, number>,
    [visibleAllUnits]
  );
  const lifecycleCounts = useMemo(
    () => Object.fromEntries(["approved", "needs_review", "superseded"].map((state) => [state, units.filter((unit) => unit.preference_audit?.state === state).length])) as Record<Exclude<PreferenceLifecycle, "all">, number>,
    [units]
  );

  const selectedDetail = selectedNode?.metadata?.unit as PreferenceUnit | undefined;
  const selectedModel = selectedNode?.metadata?.model as FusionModel | undefined;
  const selectionLabel = selection === "all" ? copy.all : selection === "fusion" ? copy.fusion : preferenceDimensionLabel(selection, language);
  const legend = [
    ...DIMENSIONS.map((dimension) => ({
      id: dimension,
          label: preferenceDimensionLabel(dimension, language),
      color: preferenceDimensionColor(dimension),
      count: countByDimension[dimension],
    })),
    { id: "fusion", label: copy.fusion, color: FUSION_COLOR, count: visibleModelCount },
  ];
  const selectRow = (row: PreferenceTableRow) => {
    setSelectedNode({
      id: row.kind === "model" ? `model:${row.id}` : row.id,
      metadata: row.kind === "model" ? { kind: "model", model: row.model } : { kind: "preference", unit: row.unit },
    });
  };
  const eventTime = (at: number) => at ? new Date(at).toLocaleString(language === "zh" ? "zh-CN" : "en-US", { hour12: false }) : "—";

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">{copy.title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {copy.intro}
          </p>
        </div>
        <div className="text-xs text-muted-foreground">
          {copy.approved} {lifecycleCounts.approved} · {copy.pending} {lifecycleCounts.needs_review} · {copy.superseded} {lifecycleCounts.superseded} · {copy.fusion} {models.length}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1 border-b border-border pb-3 text-sm">
        <span className="mr-1 text-muted-foreground">{copy.scope}</span>
        {([
          ["approved", copy.approved + " " + lifecycleCounts.approved],
          ["needs_review", copy.pending + " " + lifecycleCounts.needs_review],
          ["superseded", copy.superseded + " " + lifecycleCounts.superseded],
          ["all", copy.allRecords + " " + units.length],
        ] as const).map(([state, label]) => (
          <button key={state} type="button" onClick={() => { setLifecycle(state); setSelectedNode(null); }} className={"rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors " + (lifecycle === state ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground")}>{label}</button>
        ))}
      </div>
      {lifecycle === "needs_review" && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm leading-6 text-amber-950 dark:bg-amber-950/20 dark:text-amber-100">
          {copy.pendingExplanation}
        </p>
      )}
      {lifecycle === "superseded" && (
        <p className="rounded-md border border-slate-300 bg-muted/50 px-3 py-2 text-sm leading-6 text-muted-foreground">
          {copy.supersededExplanation}
        </p>
      )}

      <div className="flex flex-wrap gap-2 border-b border-border pb-3">
        <button
          onClick={() => {
            setSelection("all");
            setSelectedNode(null);
          }}
          className={`rounded-md border px-3 py-2 text-sm font-semibold transition-colors ${
            selection === "all" ? "bg-muted" : "hover:bg-muted/60"
          }`}
          style={{ borderColor: "#475569" }}
        >
          {copy.all} <span className="ml-1 opacity-70">{visibleAllUnits.length + visibleModelCount}</span>
        </button>
        {DIMENSIONS.map((dimension) => (
          <button
            key={dimension}
            onClick={() => {
              setSelection(dimension);
              setSelectedNode(null);
            }}
            className={`rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
              selection === dimension ? "bg-muted" : "hover:bg-muted/60"
            }`}
            style={{ borderColor: preferenceDimensionColor(dimension) }}
          >
            {preferenceDimensionLabel(dimension, language)} <span className="ml-1 opacity-70">{countByDimension[dimension]}</span>
          </button>
        ))}
        <button
          onClick={() => {
            setSelection("fusion");
            setLifecycle("approved");
            setSelectedNode(null);
          }}
          className={`rounded-md border-2 px-3 py-2 text-sm font-semibold transition-colors ${
            selection === "fusion" ? "bg-amber-50 text-amber-950 dark:bg-amber-950/30 dark:text-amber-50" : "hover:bg-amber-50/60"
          }`}
          style={{ borderColor: FUSION_COLOR }}
        >
          {copy.fusion} <span className="ml-1 opacity-70">{models.length}</span>
        </button>
      </div>

      <div className="flex flex-wrap gap-1" role="tablist" aria-label={copy.title}>
        {([
          ["constellation", copy.constellation],
          ["graph", copy.graph],
          ["table", copy.table],
          ["timeline", copy.timeline],
        ] as const).map(([mode, label]) => (
          <button
            key={mode}
            type="button"
            role="tab"
            aria-selected={viewMode === mode}
            onClick={() => setViewMode(mode)}
            className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${viewMode === mode ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading && <div className="rounded-lg border p-6 text-sm text-muted-foreground">{copy.loading}</div>}
      {error && <div className="rounded-lg border border-destructive/40 p-6 text-sm text-destructive">{error}</div>}
      {!loading && !error && (
        <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 overflow-hidden rounded-lg border bg-background">
            {viewMode === "constellation" && (
              <Constellation
                data={graph}
                height={680}
                nodeColorFn={(node) => node.color ?? "#64748b"}
                nodeSizeFn={(node) => {
                  if (node.id === "fusion-center") return 16;
                  if (node.metadata?.kind === "model") return 10;
                  return 5;
                }}
                preserveNodeColor
                linkColorFn={(link) => link.color ?? "#64748b"}
                linkOpacity={0.18}
                linkWidth={0.7}
                clusterKeyFn={(node) => (selection === "all" || selection === "fusion" ? node.group ?? null : null)}
                clusterColorFn={(group) => group === "fusion" ? FUSION_COLOR : preferenceDimensionColor(group as PreferenceDimension)}
                clusterLabelFn={(group) => group === "fusion" ? copy.fusion + " " + models.length : preferenceDimensionLabel(group as PreferenceDimension, language) + " " + countByDimension[group as PreferenceDimension]}
                centerClusterKey={selection === "all" ? "fusion" : undefined}
                onNodeClick={setSelectedNode}
              />
            )}
            {viewMode === "graph" && (
              <Graph2D
                data={graph}
                height={680}
                showLabels
                nodeColorFn={(node) => node.color ?? "#64748b"}
                nodeSizeFn={(node) => node.metadata?.kind === "model" ? 30 : node.id === "fusion-center" ? 38 : 18}
                linkColorFn={(link) => link.color ?? "#64748b"}
                linkWidthFn={(link) => link.type === "reference" ? 2 : 1}
                onNodeClick={setSelectedNode}
              />
            )}
            {viewMode === "table" && (
              <div className="max-h-[680px] overflow-auto">
                <table className="w-full text-left text-sm">
                  <thead className="sticky top-0 bg-muted text-xs text-muted-foreground">
                    <tr><th className="px-4 py-3 font-medium">{copy.kind}</th><th className="px-4 py-3 font-medium">{copy.content}</th><th className="px-4 py-3 font-medium">{copy.status}</th><th className="px-4 py-3 font-medium">{copy.time}</th></tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {tableRows.map((row) => (
                      <tr key={`${row.kind}:${row.id}`} className="cursor-pointer hover:bg-muted/60" onClick={() => selectRow(row)}>
                        <td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{row.kind === "model" ? copy.model : preferenceDimensionLabel(row.unit.primary_category, language)}</td>
                        <td className="max-w-[480px] px-4 py-3 leading-6"><span className="line-clamp-2">{row.title}</span></td>
                        <td className="px-4 py-3 text-xs"><span className="rounded border px-2 py-1">{row.lifecycle === "approved" ? copy.approved : row.lifecycle === "active" ? copy.active : row.lifecycle === "needs_review" ? copy.pending : row.lifecycle === "superseded" ? copy.superseded : row.lifecycle}</span></td>
                        <td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{eventTime(row.at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!tableRows.length && <p className="p-6 text-sm text-muted-foreground">{copy.noRows}</p>}
              </div>
            )}
            {viewMode === "timeline" && (
              <ol className="max-h-[680px] divide-y divide-border overflow-auto">
                {timelineEvents.map((event) => (
                  <li key={`${event.kind}:${event.id}`} className="cursor-pointer px-5 py-4 hover:bg-muted/60" onClick={() => selectRow(event)}>
                    <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-muted-foreground">{eventTime(event.at)}</span><span className="rounded border px-2 py-1 text-xs">{event.kind === "model" ? copy.model : event.lifecycle === "approved" ? copy.approved : copy.pending}</span></div>
                    <p className="mt-2 leading-6">{event.title}</p>
                  </li>
                ))}
                {!timelineEvents.length && <li className="p-6 text-sm text-muted-foreground">{copy.noTimeline}</li>}
              </ol>
            )}
          </div>
          <aside className="min-w-0 rounded-lg border bg-background p-4">
            <section className="border-b border-border pb-3">
              <h3 className="text-sm font-semibold">{copy.colors}</h3>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{copy.currentView} {selectionLabel}</p>
              <div className="mt-3 space-y-2">
                {legend.map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-3 text-xs">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                      <span className="truncate">{item.label}</span>
                    </span>
                    <span className="font-medium tabular-nums">{item.count}</span>
                  </div>
                ))}
              </div>
            </section>
            <section className="pt-4">
            <h3 className="text-sm font-semibold">{copy.details}</h3>
            {!selectedNode && <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy.detailHint}</p>}
            {selectedDetail && (
              <div className="mt-3 space-y-3 text-sm">
                <div className="font-medium" style={{ color: preferenceDimensionColor(selectedDetail.primary_category) }}>
                  {preferenceDimensionLabel(selectedDetail.primary_category, language)}
                </div>
                <p className="leading-6">{selectedDetail.text}</p>
                {selectedDetail.applies_when?.length ? <p className="border-l-2 pl-3 text-xs leading-5 text-muted-foreground" style={{ borderColor: preferenceDimensionColor(selectedDetail.primary_category) }}>{copy.applies} {selectedDetail.applies_when.join("；")}</p> : null}
                {selectedDetail.exceptions?.length ? <p className="border-l-2 pl-3 text-xs leading-5 text-muted-foreground" style={{ borderColor: preferenceDimensionColor(selectedDetail.primary_category) }}>{copy.exceptions} {selectedDetail.exceptions.join("；")}</p> : null}
                {selectedDetail.effect_on_action ? <p className="text-xs leading-5 text-muted-foreground">{copy.action} {selectedDetail.effect_on_action}</p> : null}
                <p className="text-xs leading-5 text-muted-foreground">{copy.status}: {selectedDetail.preference_audit?.state === "approved" ? copy.approved : selectedDetail.preference_audit?.state === "needs_review" ? copy.pending : selectedDetail.preference_audit?.state ?? "—"} · {copy.evidence} {selectedDetail.evidence_refs?.length ?? 0}</p>
              </div>
            )}
            {selectedModel && (
              <div className="mt-3 space-y-3 text-sm">
                <div className="font-medium" style={{ color: FUSION_COLOR }}>{selectedModel.title}</div>
                {selectedModel.purpose && <p className="leading-6">{selectedModel.purpose}</p>}
                <p className="leading-6">{selectedModel.mechanism ?? selectedModel.sections?.[0]?.text ?? copy.noMechanism}</p>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  {selectedModel.dimensions.map((dimension) => <span key={dimension} className="rounded border px-2 py-1" style={{ borderColor: preferenceDimensionColor(dimension), color: preferenceDimensionColor(dimension) }}>{preferenceDimensionLabel(dimension, language)}</span>)}
                </div>
                {selectedModel.sections?.map((section, index) => (
                  <div key={index} className="space-y-1 border-l-2 pl-3" style={{ borderColor: FUSION_COLOR }}>
                    {section.applies_when?.length ? <p className="text-xs leading-5 text-muted-foreground">{copy.applies} {section.applies_when.join("；")}</p> : null}
                    {section.exceptions?.length ? <p className="text-xs leading-5 text-muted-foreground">{copy.exceptions} {section.exceptions.join("；")}</p> : null}
                    {section.counterevidence?.length ? <p className="text-xs leading-5 text-muted-foreground">Counterevidence: {section.counterevidence.join("；")}</p> : null}
                  </div>
                ))}
                <p className="text-xs leading-5 text-muted-foreground">{copy.evidence} {selectedModel.sections?.flatMap((section) => section.guidance_refs ?? []).length ?? 0}{selectedModel.confidence != null ? " · " + selectedModel.confidence.toFixed(2) : ""}</p>
              </div>
            )}
            {selectedNode?.metadata?.kind === "fusion" && (
              <p className="mt-3 text-sm leading-6 text-muted-foreground">{copy.dynamicFusion}</p>
            )}
            </section>
          </aside>
        </div>
      )}
    </section>
  );
}
