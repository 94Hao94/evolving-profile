"use client";

import { useEffect, useState } from "react";
import { useLocale } from "next-intl";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";

import { inlineUiText } from "@/lib/inline-i18n";
type Group = { id: string; actor: string; count?: number | null };
type Item = { id: string; text?: string; delivered_text?: string; type?: string; reason?: string; snapshot_stage?: string; snapshot_at?: string;
  delivery?: string; text_truncated?: boolean; outcome?: string };
type Page = { items?: Item[]; total?: number; next_offset?: number | null; snapshot_status?: string; query?: string; missing_discovery_snapshot_count?:number };

export function candidateDeliveryLabel(delivery?: string) {
  if (delivery === "previously_returned_currently_blocked") return inlineUiText("当时返回过 · 来源现不可展示");
  return delivery === "text_returned" ? inlineUiText("正文已返回 · 记忆输入") :
    delivery === "locator_returned" ? inlineUiText("仅返回 ID · 导航线索") : inlineUiText("后台探测候选 · 仅审计预览，未送入 Agent");
}

const REASONS: Record<string, string> = {
  withdrawn: inlineUiText("来源已撤回"), source_unavailable: inlineUiText("来源暂不可读取"), validity_unknown: inlineUiText("来源有效性未知"),
  identity_mismatch: inlineUiText("来源身份不匹配"), insufficient_literal_overlap: inlineUiText("字面关联不足，留待 Agent 判断"),
  probe_preview_budget: inlineUiText("探测正文预算已满，未返回"), uncertain: inlineUiText("关联未确认，由 Agent 判断"),
  literal_overlap: inlineUiText("字面匹配，仅作候选线索"), literal_match: inlineUiText("完整正文包含实体词，仍需 Agent 判断"),
  official_retrieval: inlineUiText("上游检索候选"), agent_decides: inlineUiText("由 Agent 判断"),
};

export function CandidateAuditBrowser({ promptId, groups }: { promptId: string; groups: Group[] }) {
  const locale = useLocale();
  const [group, setGroup] = useState(groups[0]?.id ?? "");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Page | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!group) return;
    const abort = new AbortController();
    setLoading(true); setFailed(false); setPage(null);
    fetch(`/api/evolving-profile/guidance/prompts/${encodeURIComponent(promptId)}?candidate_group=${encodeURIComponent(group)}&offset=${offset}&limit=10`,
      { cache: "no-store", signal: abort.signal })
      .then(response => { if (!response.ok) throw new Error("candidate_page_failed"); return response.json(); })
      .then(setPage)
      .catch(error => { if (error.name !== "AbortError") setFailed(true); })
      .finally(() => { if (!abort.signal.aborted) setLoading(false); });
    return () => abort.abort();
  }, [promptId, group, offset]);
  return <section className="mt-4 min-w-0 border-t pt-3 text-xs">
    <div className="font-semibold">{inlineUiText("候选逐条审计")}</div>
    <p className="mt-1 leading-5 text-muted-foreground">{inlineUiText("后台探测候选可能有预览，但未计入 Agent 实际上下文；只有“正文已返回 · 记忆输入”才表示本轮正文送达。")}</p>
    <div className="mt-2 flex flex-wrap gap-2">{groups.map((item, index) => <button type="button" key={item.id}
      onClick={() => { setGroup(item.id); setOffset(0); }} aria-pressed={item.id === group}
      className={`inline-flex items-center gap-1 border-b-2 px-1 py-2 ${item.id === group ? "border-primary text-primary" : "border-transparent text-muted-foreground"}`}>
      <Search className="h-3 w-3" />{item.actor === "system_probe" ? inlineUiText("系统探测") : `Agent 检索 ${index + 1}`} · {item.count ?? inlineUiText("未知")} 条
    </button>)}</div>
    {page?.query ? <p className="mt-2 break-words leading-5">{inlineUiText("查询：")}{page.query}</p> : null}
    {loading ? <p className="py-4 text-muted-foreground">{inlineUiText("正在读取候选快照…")}</p> : null}
    {failed ? <p className="py-4 text-destructive">{inlineUiText("候选快照读取失败。")}</p> : null}
    {page?.snapshot_status === "historical_snapshot_missing" ? <p className="py-4 text-amber-700">{inlineUiText("这条旧记录未保存候选正文快照；不能用重新检索的内容冒充当时结果。")}</p> : null}
    {page?.snapshot_status === "partial_history" ? <p className="py-4 text-amber-700">有 {page.missing_discovery_snapshot_count} {inlineUiText("条缺少当时的发现快照；后续源读取内容单独标记，不替代旧记录。")}</p> : null}
    {page?.snapshot_status === "source_receipt_unavailable" || page?.snapshot_status === "not_bound_to_prompt" ? <p className="py-4 text-amber-700">{inlineUiText("本 Prompt 的候选回执暂不可读取或归属未确认。")}</p> : null}
    {page?.items?.map((item, index) => <details key={item.id} className="border-b py-3">
      <summary className="cursor-pointer leading-5 break-words"><span className="mr-1 text-muted-foreground">{offset + index + 1}.</span>
        <span className="font-medium">{candidateDeliveryLabel(item.delivery)}</span>
        <div className="mt-1">{item.text?.slice(0, 160) || inlineUiText("未保存可展示正文")}</div>
      </summary>
      <div className="mt-2 space-y-2 leading-5 break-words">
        <p>{inlineUiText("处理原因：")}{REASONS[item.reason ?? ""] ?? item.reason ?? inlineUiText("未记录")}</p>
        <p className="whitespace-pre-wrap">{item.snapshot_stage === "source_read" ? inlineUiText("后续源读取预览（非当时发现快照）") : inlineUiText("检索时预览")}：{item.text || inlineUiText("无正文")}{item.text_truncated ? inlineUiText("（预览截断）") : ""}</p>
        {item.snapshot_at ? <p className="text-muted-foreground">{inlineUiText("快照时间：")}{new Date(item.snapshot_at).toLocaleString(locale.startsWith("zh") ? locale : "en-US")}</p> : null}
        {item.delivery === "text_returned" ? <p className="whitespace-pre-wrap">{inlineUiText("实际返回给 Agent：")}{item.delivered_text || inlineUiText("历史回执未保存片段")}</p> : null}
        <p className="font-mono text-[10px] text-muted-foreground break-all">{inlineUiText("来源 ID：")}{item.id}</p>
      </div>
    </details>)}
    {page && (page.total != null && page.items?.length) ? <div className="mt-3 flex items-center justify-between">
      <span>{page.total ? `${offset + 1}–${Math.min(offset + 10, page.total)}` : "0"} / {page.total ?? 0} 条</span>
      <div className="flex gap-2"><button type="button" title={inlineUiText("上一页候选")} aria-label={inlineUiText("上一页候选")} disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 10))} className="border p-1 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
        <button type="button" title={inlineUiText("下一页候选")} aria-label={inlineUiText("下一页候选")} disabled={loading || page.next_offset == null} onClick={() => setOffset(page.next_offset ?? offset)} className="border p-1 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button></div>
    </div> : null}
  </section>;
}
