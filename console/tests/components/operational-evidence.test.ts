import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";
import en from "@/messages/en.json";
import zh from "@/messages/zh-CN.json";
import { OperationalAttemptHistory, OperationalEvidenceSummary } from "@/components/operational-overview";
import * as components from "@/components/operational-overview";

const scan = { llmFailures: { returned: 100, total: 190, coverage: "partial" as const }, llmFailureGroups: { total: 41 }, failedOperations: { returned: 4, total: 4, coverage: "complete" as const }, relatedSuccess: { coverage: "partial" } };
const render = (locale: "en" | "zh-CN", pipeline = { state: "critical" as const, failedMemories: 8, pendingMemories: 17130 }) => renderToStaticMarkup(createElement(NextIntlClientProvider, { locale, messages: locale === "en" ? en : zh, children: createElement(OperationalEvidenceSummary, { scan, pipeline }) }));
describe("operational evidence summary", () => {
  it.each(["en", "zh-CN"] as const)("renders failed batches and isolated records separately from fresh dispatcher health in %s", locale => {
    const pipeline = { state: "warning", failedMemories: 0, pendingMemories: 0, failedBatches: 2, failedTaskRows: 4,
      localRetention: { status: "observed", observedAt: "2026-10-13T11:00:00Z", quarantinedRecords: 18, inflightRecords: 0, pendingRecords: 0, heldRecords: 18,
        quarantineBatches: [{ operationId: "parent-a", count: 18, at: "2026-10-13T10:00:00Z" }], dispatcher: { status: "observed", activity: "idle", at: "2026-10-13T11:00:00Z" } } };
    const html = renderToStaticMarkup(createElement(NextIntlClientProvider, { locale, timeZone: "Asia/Shanghai", messages: locale === "en" ? en : zh,
      children: createElement(OperationalEvidenceSummary, { scan, pipeline } as any) }));
    expect(html).toContain(locale === "en" ? "2 failed batches" : "2 个失败批次");
    expect(html).toContain(locale === "en" ? "18 isolated queue records" : "18 条已隔离队列记录");
    expect(html).toContain(locale === "en" ? "Host dispatcher" : "本机调度器");
    expect(html).toContain(locale === "en" ? "Idle" : "空闲");
    expect(html).toContain(locale === "en" ? "Raw queue records are preserved" : "队列原始记录保留");
  });

  it("shows unavailable queue counts and a stale dispatcher without presenting either as zero or healthy", () => {
    const html = renderToStaticMarkup(createElement(NextIntlClientProvider, { locale: "en", timeZone: "UTC", messages: en,
      children: createElement(OperationalEvidenceSummary, { scan, pipeline: { state: "unknown", failedMemories: null, pendingMemories: null, failedBatches: null,
        localRetention: { status: "unavailable", quarantinedRecords: null, pendingRecords: null, inflightRecords: null, heldRecords: null, observedAt: null, quarantineBatches: [],
          dispatcher: { status: "stale", activity: "idle", at: "2026-10-13T10:00:00Z" } } } } as any) }));
    expect(html).toContain("Queue metadata unavailable");
    expect(html).toContain("Dispatcher receipt stale");
    expect(html).not.toContain("0 isolated queue records");
    expect(html).not.toContain("Host dispatcher · Idle");
  });
  it.each(["en", "zh-CN"] as const)("shows updating instead of unverified on a brief map refresh in %s", locale => {
    const html = renderToStaticMarkup(createElement(NextIntlClientProvider, { locale, timeZone: "UTC", messages: locale === "en" ? en : zh,
      children: createElement(components.OperationalLaneCard, { lane: { id: "map", state: "unknown", label: "地图更新", summary: "", summaryKey: "mapUpdating", incidentCount: 0, detail: "", lastObservedAt: null,
        checks: [{ label: "结构目录", state: "healthy", detail: "", detailKey: "mapUpdating", at: null }] }, pipeline: { state: "unknown", failedMemories: null, pendingMemories: null }, acknowledged: false,
        onDetail: () => {}, onToggleAcknowledgement: async () => {}, disabled: false }) }));
    expect(html).toContain(locale === "en" ? "Updating" : "更新中");
    expect(html).not.toContain(locale === "en" ? "Unverified" : "未核验");
  });
  it("removes red emphasis for a confirmed pipeline without hiding real failed or pending counts", () => {
    const html=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale:"zh-CN",timeZone:"Asia/Shanghai",messages:zh,children:createElement(OperationalEvidenceSummary,{scan,pipeline:{state:"critical",failedMemories:1,pendingMemories:100},acknowledged:true} as any)}));
    expect(html).not.toContain("bg-rose-50");
    expect(html).toContain("已确认");
    expect(html).toContain("1 条失败源记忆");
    expect(html).toContain("100 条待处理源记忆");
  });
  it("renders a confirmed lane with separate detail and restore buttons, no nested buttons",()=>{
    const Card=(components as any).OperationalLaneCard;
    const html=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale:"zh-CN",timeZone:"Asia/Shanghai",messages:zh,children:Card?createElement(Card,{lane:{id:"retention",state:"critical",incidentCount:1,checks:[],summary:"失败",detail:"",lastObservedAt:null,label:"记忆加工"},incident:{id:"retention:failed-memories",category:"retention",count:1,titleKey:"failedMemories"},pipeline:{failedMemories:1,pendingMemories:100},acknowledged:true,onDetail:()=>{},onToggleAcknowledgement:async()=>{},disabled:false}):null}));
    expect(html).toContain("已确认 · 1 条待恢复");
    expect(html).toContain("恢复本次提醒");
    expect(html).not.toContain("border-rose-500");
    expect(html).not.toMatch(/<button[^>]*>(?:(?!<\/button>)[\s\S])*<button/);
  });
  it("can hide the cleared historical summary without hiding live failures",()=>{
    const html=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale:"en",timeZone:"Asia/Shanghai",messages:en,children:createElement(OperationalEvidenceSummary,{scan,pipeline:{state:"critical",failedMemories:8,pendingMemories:17130},showHistory:false})}));
    expect(html).not.toContain("190 failed attempts");
    expect(html).toContain("8 failed source memories");
    expect(html).toContain("17,130 pending source memories");
  });
  it("shows attempt totals separately from sampled trace groups and current memory backlog", () => {
    const html = render("en");
    expect(html).toContain("190 failed attempts");
    expect(html).toContain("100 inspected");
    expect(html).toContain("41 trace jobs");
    expect(html).toContain("8 failed source memories");
    expect(html).toContain("17,130 pending source memories");
    expect(html).toContain("Partial coverage");
    expect(html).toContain("Source-document audit not performed");
  });
  it("renders readable Chinese evidence and coverage labels", () => {
    const html = render("zh-CN");
    expect(html).toContain("190 次失败尝试");
    expect(html).toContain("41 个轨迹任务");
    expect(html).toContain("覆盖不完整");
    expect(html).toContain("8 条失败源记忆");
  });
  it.each(["en", "zh-CN"])("keeps grouped history collapsed while exposing its localized expansion summary in %s", (locale) => {
    const html = renderToStaticMarkup(createElement(NextIntlClientProvider, {
      locale, messages: locale === "en" ? en : zh,
      children: createElement(OperationalAttemptHistory, {
        groups: [{ id: "g-1", traceId: "trace-a", operation: "consolidation", scope: "consolidation", errorClass: "schema_validation", attemptCount: 2, requestIds: ["request-1", "request-2"], at: "2026-10-08T10:00:00Z", recovery: "unresolved", traceComplete: false, laterSuccessId: null }],
        onSelect: () => {},
      }),
    }));
    expect(html).toMatch(/<details[^>]*>/);
    expect(html).not.toMatch(/<details[^>]*\sopen(?:\s|=|>)/);
    expect(html).toContain(locale === "en" ? "Inspect historical failure groups (1)" : "查看历史失败分组（1 组）");
    expect(html).toContain("trace-a");
    expect(html).toContain("type=\"button\"");
  });
});
