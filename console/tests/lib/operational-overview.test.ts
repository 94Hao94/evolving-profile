import { describe, expect, it } from "vitest";
import { buildOperationalOverview } from "@/lib/operational-overview";

const now = Date.parse("2026-09-20T12:00:00Z");
const runtime = {
  model: { provider: "openai", model: "qwen3.7-plus", apiKey: "configured" },
  services: [{ name: "EP API", status: "healthy", detail: "ok", url: "http://localhost" }],
  backup: { local: { status: "healthy", setCount: 2, latestAt: "2026-09-20T03:25:00Z", latestBytes: 1_500_000_000, latestVerified: true, artifacts: { database: true, config: true, capture: true } }, job: { loaded: true, lastExitCode: 0, schedule: "每日 03:25" }, cloud: { status: "unverified", mirrorSetCount: 0, latestAt: null, ageHours: null } },
};

describe("operational overview", () => {
  it("shows yesterday's failed backup even when a later backup succeeded", () => {
    const view = buildOperationalOverview({ now, runtime, backupEvents: [
      { at: "2026-09-19T15:00:00Z", status: "failed", code: "backup_exit_1", detail: "数据库导出失败" },
      { at: "2026-09-20T03:25:00Z", status: "completed", code: "backup_ok", detail: "已完成" },
    ], llm: { status: "observed", items: [] }, operations: { status: "observed", items: [] }, map: { status: "ready", checked_at: "2026-09-20T11:59:00Z" } });
    expect(view.incidents.some((issue) => issue.category === "backup" && issue.detail.includes("数据库导出失败"))).toBe(true);
    expect(view.incidents.find((issue) => issue.category === "backup")?.at).toBe("2026-09-19T15:00:00Z");
  });

  it("does not call a configured API key connected without a successful request", () => {
    const view = buildOperationalOverview({ now, runtime, backupEvents: [], llm: { status: "unavailable", items: [] }, operations: { status: "observed", items: [] }, map: { status: "ready", checked_at: "2026-09-20T11:59:00Z" } });
    expect(view.lanes.find((lane) => lane.id === "model")?.state).toBe("unknown");
    expect(view.lanes.find((lane) => lane.id === "model")?.summary).toMatch(/未核验/);
  });

  it("reports recent retain and model errors with exact trace locators but no secret", () => {
    const view = buildOperationalOverview({ now, runtime, backupEvents: [], map: { status: "ready", checked_at: "2026-09-20T11:59:00Z" }, llm: { status: "observed", items: [{ id: "trace-1", operation: "retain", status: "error", started_at: "2026-09-20T10:00:00Z", error: { code: "auth_failed", message: "Bearer SECRET" } }] }, operations: { status: "observed", items: [{ id: "op-1", task_type: "retain", status: "failed", created_at: "2026-09-20T10:01:00Z", error_message: "retain timeout" }] } });
    expect(view.incidents.map((issue) => issue.sourceId)).toEqual(expect.arrayContaining(["trace-1", "op-1"]));
    expect(JSON.stringify(view)).not.toContain("SECRET");
  });

  it("distinguishes stale and unobserved sources from healthy", () => {
    const view = buildOperationalOverview({ now, runtime, backupEvents: [], map: { status: "failed", checked_at: "2026-09-20T10:00:00Z", error_type: "TimeoutError" }, llm: { status: "observed", items: [] }, operations: { status: "unavailable", items: [] } });
    expect(view.lanes.find((lane) => lane.id === "map")?.state).toBe("warning");
    expect(view.lanes.find((lane) => lane.id === "retention")?.state).toBe("unknown");
    expect(view.overall).not.toBe("healthy");
  });

  it("marks a successful directory check stale when it stops updating", () => {
    const view = buildOperationalOverview({ now, runtime, backupEvents: [], map: { status: "ready", checked_at: "2026-09-20T11:30:00Z", stale_after_seconds: 180, semantic_status: "pending_or_stale" }, llm: { status: "observed", items: [] }, operations: { status: "observed", items: [] } });
    expect(view.incidents.some((issue) => issue.category === "map" && issue.detail.includes("过期"))).toBe(true);
  });

  it("surfaces a failed semantic refresh while keeping the structure map available", () => {
    const view = buildOperationalOverview({ now, runtime, backupEvents: [], map: { status: "ready", checked_at: "2026-09-20T11:59:00Z", semantic_status: "fresh_with_pending_changes", semantic_worker_status: "failed", semantic_error_type: "ValueError" }, llm: { status: "observed", items: [] }, operations: { status: "observed", items: [] } });
    expect(view.incidents.some((issue) => issue.category === "map" && issue.title === "语义地图加工失败")).toBe(true);
    expect(view.incidents.find((issue) => issue.title === "语义地图加工失败")?.detail).toContain("结构目录仍可用");
  });

  it("splits local and cloud backup status and exposes concrete success evidence", () => {
    const view = buildOperationalOverview({ now, runtime, backupEvents: [], map: { status: "ready", checked_at: "2026-09-20T11:59:00Z", semantic_status: "ready", semantic_worker_status: "published" }, llm: { status: "observed", items: [{ id: "llm-ok", operation: "retain", status: "success", started_at: "2026-09-20T11:40:00Z" }] }, operations: { status: "observed", items: [{ id: "retain-ok", task_type: "retain", status: "completed", created_at: "2026-09-20T11:30:00Z" }] } });
    const backup = view.lanes.find((lane) => lane.id === "backup");
    expect(backup?.checks.map((check) => [check.label, check.state])).toEqual([["本地", "healthy"], ["云端", "warning"]]);
    expect(backup?.checks[0].detail).toContain("2 套");
    expect(view.lanes.find((lane) => lane.id === "model")?.detail).toContain("qwen3.7-plus");
    expect(view.lanes.find((lane) => lane.id === "retention")?.detail).toContain("retain-ok");
    expect(view.lanes.find((lane) => lane.id === "map")?.detail).toContain("19:59");
  });
});
