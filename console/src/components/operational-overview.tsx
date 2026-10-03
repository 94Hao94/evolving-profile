"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { useBank } from "@/lib/bank-context";
import { bankRoute } from "@/lib/bank-url";
import { AlertTriangle, ArrowRight, CircleAlert, CircleCheck, CircleHelp, RefreshCw, Settings2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { OperationalIncident, OperationalLane } from "@/lib/operational-overview";

import { inlineUiText } from "@/lib/inline-i18n";
type Overview = {
  overall: "healthy" | "warning" | "critical" | "unknown";
  generatedAt: string;
  windowHours: number;
  lanes: OperationalLane[];
  incidents: OperationalIncident[];
  scan?: { llmFailures: { returned: number; total: number | null }; failedOperations: { returned: number; total: number | null } };
};

const TONES = {
  healthy: "text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-900",
  warning: "text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-900",
  critical: "text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-900",
  unknown: "text-zinc-600 dark:text-zinc-300 bg-zinc-50 dark:bg-zinc-900 border-zinc-200 dark:border-zinc-700",
};
const LABELS = { healthy: "正常", warning: "需关注", critical: "故障", unknown: "未核验" };
const ICONS = { healthy: CircleCheck, warning: AlertTriangle, critical: CircleAlert, unknown: CircleHelp };
const CARD_TONE = {
  healthy: "border-emerald-300 bg-emerald-50/80 dark:border-emerald-900 dark:bg-emerald-950/30",
  warning: "border-amber-400 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/35",
  critical: "border-rose-500 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/40",
  unknown: "border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900",
};
const DOT_TONE = { healthy: "bg-emerald-500", warning: "bg-amber-500", critical: "bg-rose-600", unknown: "bg-zinc-400" };

function time(value: string | null | undefined, locale = "en") {
  if (!value) return inlineUiText("时间未记录");
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString(locale.startsWith("zh") ? locale : "en-US", { hour12: false }) : inlineUiText("时间无效");
}

function operationalText(value: string | undefined, english: boolean): string {
  if (!value) return "";
  if (!english) return value
    .replaceAll("Healthy", "正常")
    .replaceAll("healthy", "正常")
    .replaceAll("current request origin", "当前请求来源")
    .replaceAll("Controller recovery lanes + runtime guidance refresh", "Controller 恢复链路 + 运行指导刷新")
    .replaceAll("Items need attention", "有项目需要关注")
    .replaceAll("Cloud mirror not verified", "云端镜像未核验");
  return value
    .replaceAll("备份与恢复", "Backup and recovery")
    .replaceAll("云端镜像未核验", "Cloud mirror not verified")
    .replaceAll("模型与 API Key", "Models and API keys")
    .replaceAll("记忆保留", "Memory retention")
    .replaceAll("地图更新", "Map update")
    .replaceAll("本地", "Local")
    .replaceAll("云端", "Cloud")
    .replaceAll("最新", "Latest")
    .replaceAll("最近成功", "Recent success")
    .replaceAll("最近完成", "Recent completion")
    .replaceAll("最近核对", "Last checked")
    .replaceAll("已滞后", "Stale")
    .replaceAll("校验完整", "Checksum verified")
    .replaceAll("已覆盖当前源版本", "Current source version covered")
    .replaceAll("结构目录", "Structure catalog")
    .replaceAll("语义目录", "Semantic catalog")
    .replaceAll("已探测服务在线", "Service detected online")
    .replace(/(\d+(?:\.\d+)?)\s*套/g, "$1 sets")
    .replace(/(\d+(?:\.\d+)?)\s*小时/g, "$1 hours")
    .replace(/(\d+(?:\.\d+)?)\s*条/g, "$1 items")
    .replace(/：/g, ": ")
    .replace(/\s+/g, " ")
    .trim();
}

export function OperationalOverview() {
  const { currentBank: bankId } = useBank();
  const locale = useLocale();
  const english = !locale.startsWith("zh");
  const router = useRouter();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<OperationalIncident | null>(null);
  const [policyOpen, setPolicyOpen] = useState(false);

  const load = useCallback(async () => {
    if (!bankId) return;
    try {
      const response = await fetch(`/api/evolving-profile/overview/${encodeURIComponent(bankId)}`, { cache: "no-store" });
      if (!response.ok) throw new Error("overview_unavailable");
      setData(await response.json()); setError(false);
    } catch { setError(true); }
    finally { setLoading(false); }
  }, [bankId]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const openDetail = (incident: OperationalIncident) => setSelected(incident);
  const navigate = (incident: OperationalIncident) => {
    if (!bankId) return;
    const suffix = incident.action === "flow" ? "?view=flow" : incident.action === "llm-requests" ? "?view=profile&bankConfigTab=llm-requests" : incident.action === "operations" ? "?view=profile&bankConfigTab=general#bank-operations" : "?view=profile&bankConfigTab=configuration";
    setSelected(null);
    router.push(bankRoute(bankId, suffix));
  };

  const overall = data?.overall ?? "unknown";
  const OverallIcon = ICONS[overall];
  return (
    <section className="mb-7 space-y-4" aria-label={inlineUiText("运行总览")}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
        <div>
          <h2 className="text-lg font-semibold">{inlineUiText("运行总览")}</h2>
          <p className="text-xs text-muted-foreground">{data ? (english ? `Last 24 hours · Updated ${time(data.generatedAt, locale)}` : `最近 24 小时 · 更新于 ${time(data.generatedAt, locale)}`) : (english ? "Last 24 hours · Loading" : "最近 24 小时 · 正在读取")}</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="inline-flex h-9 w-9 items-center justify-center rounded border hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary" title={inlineUiText("预警口径")} aria-label={inlineUiText("预警口径")} onClick={() => setPolicyOpen(true)}><Settings2 className="h-4 w-4" /></button>
          <button type="button" className="inline-flex h-9 w-9 items-center justify-center rounded border hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary" title={inlineUiText("刷新运行总览")} aria-label={inlineUiText("刷新运行总览")} onClick={() => void load()}><RefreshCw className="h-4 w-4" /></button>
        </div>
      </div>
      {error && <p role="alert" className="text-sm text-rose-700">{inlineUiText("运行状态读取失败，现有数据可能已过期。")}</p>}
      <div className={`flex items-center gap-3 rounded border p-3 ${TONES[overall]}`}>
        <OverallIcon className="h-5 w-5 shrink-0" />
        <div className="min-w-0"><div className="text-sm font-semibold">{loading && !data ? inlineUiText("正在核对系统状态") : overall === "healthy" ? inlineUiText("已核验的链路正常") : overall === "critical" ? inlineUiText("有故障需要处理") : overall === "warning" ? inlineUiText("有项目需要关注") : inlineUiText("有项目尚未核验")}</div>
          <div className="text-xs">{data ? (english ? `${data.incidents.length} issues or unverified items · ${data.lanes.filter((lane) => lane.state === "healthy").length}/${data.lanes.length} lanes verified healthy` : `${data.incidents.length} 条问题与未核验项 · ${data.lanes.filter((lane) => lane.state === "healthy").length}/${data.lanes.length} 条链路已核验正常`) : (english ? "Reading services and receipts" : "读取服务和回执中")}</div></div>
      </div>
      {data && <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {data.lanes.map((lane) => {
          const Icon = ICONS[lane.state];
          const incident = data.incidents.find((item) => item.category === lane.id);
          return <button type="button" key={lane.id} onClick={() => incident && openDetail(incident)} disabled={!incident}
            className={`min-h-36 rounded border-t-4 border-x border-b p-3 text-left shadow-sm disabled:cursor-default enabled:hover:brightness-[0.98] focus-visible:relative focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-primary ${CARD_TONE[lane.state]}`}>
            <div className="flex items-center justify-between gap-2 text-xs font-medium text-muted-foreground"><span>{lane.label}</span><Icon className={`h-4 w-4 ${TONES[lane.state].split(" ")[0]}`} /></div>
            <div className={`mt-2 text-base font-bold ${TONES[lane.state].split(" ")[0]}`}>{english ? ({ healthy: "Healthy", warning: "Needs attention", critical: "Failure", unknown: "Unverified" } as Record<string, string>)[lane.state] : LABELS[lane.state]}{lane.incidentCount > 0 ? ` · ${lane.incidentCount}` : ""}</div>
            <div className="mt-1 text-xs font-medium leading-5 text-foreground">{operationalText(lane.summary, english)}</div>
            <div className="mt-2 space-y-1.5 border-t border-current/15 pt-2">
              {lane.checks.map((check) => <div key={`${lane.id}:${check.label}`} className="flex items-start gap-2 text-[11px] leading-4">
                <span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${DOT_TONE[check.state]}`} />
                <span className="min-w-0"><strong className="font-semibold">{operationalText(check.label, english)}</strong><span className="text-muted-foreground"> · {operationalText(check.detail, english)}</span></span>
              </div>)}
            </div>
          </button>;
        })}
      </div>}

      {data && <div className="border-t border-border pt-4">
        <div className="flex items-baseline justify-between gap-3"><h3 className="text-sm font-semibold">{inlineUiText("最近 24 小时的问题")}</h3><span className="text-xs text-muted-foreground">{data.incidents.length} {english ? (data.incidents.length === 1 ? "item" : "items") : "项"}</span></div>
        <div className="mt-2 divide-y divide-border border-y border-border">
          {data.incidents.length ? data.incidents.map((incident) => {
            const Icon = ICONS[incident.severity];
            return <button type="button" key={incident.id} onClick={() => openDetail(incident)} className="flex w-full items-center gap-3 py-3 text-left hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-primary">
              <Icon className={`h-4 w-4 shrink-0 ${TONES[incident.severity].split(" ")[0]}`} />
              <span className="min-w-0 flex-1"><span className="block text-sm font-medium">{incident.title}</span><span className="block truncate text-xs text-muted-foreground">{incident.detail}</span></span>
              <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">{time(incident.at, locale)}</span><ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>;
          }) : <p className="py-4 text-sm text-muted-foreground">{inlineUiText("最近 24 小时没有观测到失败回执。未核验链路仍显示在上方，不等于全部正常。")}</p>}
        </div>
        {((data.scan?.llmFailures.total ?? 0) > (data.scan?.llmFailures.returned ?? 0) || (data.scan?.failedOperations.total ?? 0) > (data.scan?.failedOperations.returned ?? 0)) &&
          <p className="mt-2 text-xs text-amber-800">{inlineUiText("列表按数据源分页展示；还有较早记录未展开，请到操作或模型请求页继续查看。")}</p>}
      </div>}

      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader><DialogTitle>{selected?.title}</DialogTitle><DialogDescription>{selected ? time(selected.at, locale) : ""}</DialogDescription></DialogHeader>
          {selected && <div className="space-y-3 text-sm">
            <p className="break-words leading-6">{selected.detail}</p>
            <dl className="grid grid-cols-[80px_1fr] gap-2 border-t border-border pt-3 text-xs"><dt className="text-muted-foreground">{inlineUiText("证据来源")}</dt><dd className="break-all">{selected.source}</dd><dt className="text-muted-foreground">{inlineUiText("记录 ID")}</dt><dd className="break-all font-mono">{selected.sourceId ?? inlineUiText("未提供")}</dd><dt className="text-muted-foreground">{inlineUiText("级别")}</dt><dd>{english ? ({ healthy: "Healthy", warning: "Needs attention", critical: "Failure", unknown: "Unverified" } as Record<string, string>)[selected.severity] : LABELS[selected.severity]}</dd></dl>
            <button type="button" className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline" onClick={() => navigate(selected)}>{inlineUiText("查看对应页面")} <ArrowRight className="h-4 w-4" /></button>
          </div>}
        </DialogContent>
      </Dialog>
      <Dialog open={policyOpen} onOpenChange={setPolicyOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader><DialogTitle>{inlineUiText("预警口径")}</DialogTitle><DialogDescription>{inlineUiText("概览只根据可回读证据判断，不以配置存在代替真实可用。")}</DialogDescription></DialogHeader>
          <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-3 text-sm">
            <dt className="text-muted-foreground">{inlineUiText("观察窗口")}</dt><dd>{inlineUiText("最近 24 小时")}</dd>
            <dt className="text-muted-foreground">{inlineUiText("备份")}</dt><dd>{inlineUiText("计划退出失败、最新备份超过 24 小时、缺少数据库/配置/校验清单均提示；云端未回读标为未核验。")}</dd>
            <dt className="text-muted-foreground">{inlineUiText("模型连接")}</dt><dd>{inlineUiText("最近成功请求才标正常；只配置 API Key 仍显示未核验。")}</dd>
            <dt className="text-muted-foreground">{inlineUiText("记忆保留")}</dt><dd>{inlineUiText("失败操作提示故障；最近有完成回执才标正常。")}</dd>
            <dt className="text-muted-foreground">{inlineUiText("地图")}</dt><dd>{inlineUiText("结构目录超过 3 分钟未核对提示过期；模型语义更新超过 20 分钟仍未完成才提示。")}</dd>
          </dl>
          <button type="button" className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline" onClick={() => { setPolicyOpen(false); if (bankId) router.push(bankRoute(bankId, "?view=profile&bankConfigTab=configuration")); }}>{inlineUiText("打开运行配置")} <ArrowRight className="h-4 w-4" /></button>
        </DialogContent>
      </Dialog>
    </section>
  );
}
