import { afterEach, describe, expect, it, vi } from "vitest";
const files = vi.hoisted(() => new Map<string, unknown>());
vi.mock("@/app/api/evolving-profile/runtime/route", () => ({ GET: async () => Response.json({ services: [] }) }));
vi.mock("@/lib/evolving-client", () => ({ dataplaneBankUrl: (bank: string, path: string) => `http://bank/${bank}${path}`, getDataplaneHeaders: () => ({}) }));
vi.mock("node:fs/promises", () => ({ readFile: async (path: string) => {
  for (const [suffix, value] of files) if (path.endsWith(suffix)) return JSON.stringify(value);
  throw Object.assign(new Error("missing"), { code: "ENOENT" });
} }));
import { GET } from "@/app/api/evolving-profile/overview/[bankId]/route";

afterEach(() => { vi.unstubAllGlobals(); files.clear(); });

describe("overview evidence route", () => {
  it("projects explicit backend lineage and only selected-Bank queue metadata, keeping the global dispatcher separate", async () => {
    const at = new Date(Date.now() - 1000).toISOString();
    files.set("retention/worker-state.json", { status: "idle", at, queue_items: 999, quarantined_items: 999, retry_counts: { SECRET: 3 } });
    files.set("codex/state/retention-queue.json", { version: 1, sessions: { PRIVATE: 3 }, items: [
      { id: "q-a", bank_id: "bank-a", content: "PRIVATE SOURCE", session_id: "PRIVATE SESSION", retention_quarantine: { operation_id: "parent-a", at, reason: "retention_retry_exhausted:failed" }, retention_origin_hold: "held" },
      { id: "q-other", bank_id: "other-bank", content: "OTHER PRIVATE SOURCE", retention_quarantine: { operation_id: "other-op", at } },
    ] });
    vi.stubGlobal("fetch", async (value: string) => {
      const url = new URL(value);
      if (url.pathname.endsWith("/stats")) return Response.json({ failed_consolidation: 0, pending_consolidation: 0 });
      if (url.pathname.endsWith("/operations")) return Response.json({ total: 2, operations: url.searchParams.get("status") === "failed" ? [
        { id: "parent-a", task_type: "batch_retain", status: "failed", created_at: at },
        { id: "child-a", parent_operation_id: "parent-a", task_type: "retain", status: "failed", created_at: at, result_metadata: { content: "PRIVATE SOURCE" } },
      ] : [] });
      return Response.json({ items: [], total: 0 });
    });
    const body = await (await GET(new Request("http://console/overview/bank-a"), { params: Promise.resolve({ bankId: "bank-a" }) })).json();
    expect(body.pipeline.failedBatches).toBe(1);
    expect(body.pipeline.localRetention).toMatchObject({ status: "observed", quarantinedRecords: 1, inflightRecords: 0, pendingRecords: 0,
      quarantineBatches: [{ operationId: "parent-a", count: 1, at }], dispatcher: { status: "observed", activity: "idle", at } });
    expect(JSON.stringify(body)).not.toMatch(/PRIVATE|SECRET|other-op|other-bank|999|result_metadata/);
  });

  it("reports stale dispatcher receipts and malformed queue evidence explicitly without inventing zero counts", async () => {
    files.set("retention/worker-state.json", { status: "idle", at: new Date(Date.now() - 600_000).toISOString() });
    files.set("codex/state/retention-queue.json", { items: [{ bank_id: null, retention_quarantine: {} }] });
    vi.stubGlobal("fetch", async (value: string) => new URL(value).pathname.endsWith("/operations") ? Response.json({ operations: [], total: 0 }) : Response.json({ items: [], total: 0 }));
    const body = await (await GET(new Request("http://console/overview/bank-a"), { params: Promise.resolve({ bankId: "bank-a" }) })).json();
    expect(body.pipeline.localRetention).toMatchObject({ status: "unavailable", quarantinedRecords: null, pendingRecords: null, dispatcher: { status: "stale", activity: "idle" } });
  });
  it("rejects malformed selected-Bank operation bindings instead of treating them as pending records", async () => {
    files.set("codex/state/retention-queue.json", { items: [{ bank_id: "bank-a", operation_id: { content: "PRIVATE" } }] });
    vi.stubGlobal("fetch", async () => Response.json({ operations: [], items: [], total: 0 }));
    const body = await (await GET(new Request("http://console/overview/bank-a"), { params: Promise.resolve({ bankId: "bank-a" }) })).json();
    expect(body.pipeline.localRetention.status).toBe("unavailable");
    expect(body.pipeline.localRetention.inflightRecords).toBeNull();
  });
  it("pages failures, reads exact run counts and bank backlog, and reconciles success by trace without returning prompts", async () => {
    const now = Date.now();
    const calls: URL[] = [];
    vi.stubGlobal("fetch", async (value: string) => {
      const url = new URL(value); calls.push(url);
      const q = url.searchParams;
      if (url.pathname.endsWith("/stats")) return Response.json({ failed_consolidation: 8, pending_consolidation: 17130 });
      if (url.pathname.endsWith("/operations")) return Response.json({ operations: [], total: 0 });
      if (q.get("group") === "true") return Response.json({ items: [], total: 41 });
      if (q.get("trace_id")) return Response.json({ total: 1, items: [{ id: "success-a", trace_id: "trace-a", operation: "consolidation", scope: "consolidation", status: "success", started_at: new Date(now - 1000).toISOString(), input: "PRIVATE DOCUMENT BODY" }] });
      if (q.get("status") === "success") return Response.json({ total: 1, items: [{ id: "unrelated", trace_id: "trace-b", operation: "retain", status: "success", started_at: new Date(now - 500).toISOString() }] });
      const offset = Number(q.get("offset") ?? 0);
      const count = Math.min(100, 190 - offset);
      return Response.json({ total: 190, items: Array.from({ length: Math.max(0, count) }, (_, i) => ({ id: `failure-${offset + i}`, trace_id: "trace-a", operation: "consolidation", scope: "consolidation", status: "error", started_at: new Date(now - 5000).toISOString(), error: "ValidationError: Field required", input: "PRIVATE DOCUMENT BODY" })) });
    });
    const response = await GET(new Request("http://console/overview/bank-a"), { params: Promise.resolve({ bankId: "bank-a" }) });
    const body = await response.json();
    expect(body.scan.llmFailures).toMatchObject({ returned: 190, total: 190, coverage: "complete" });
    expect(body.scan.llmFailureGroups.total).toBe(41);
    expect(body.pipeline.failedMemories).toBe(8);
    expect(body.attemptHistory[0].recovery).toBe("later_attempt_succeeded");
    expect(JSON.stringify(body)).not.toContain("PRIVATE DOCUMENT BODY");
    expect(calls.some((url) => url.searchParams.get("trace_id") === "trace-a")).toBe(true);
    expect(calls.every((url) => !url.pathname.includes("/documents"))).toBe(true);
    const traceReads = calls.filter((url) => url.pathname.endsWith("/llm-requests"));
    expect(traceReads.length).toBeGreaterThan(0);
    expect(traceReads.every((url) => url.searchParams.get("include_content") === "false")).toBe(true);
    const counter = traceReads.find((url) => url.searchParams.get("group") === "true");
    expect(counter?.searchParams.get("count_only")).toBe("true");
  });
  it("does not turn a malformed source payload into an observed empty source", async () => {
    vi.stubGlobal("fetch", async () => Response.json({ error: "no usable inventory" }));
    const response = await GET(new Request("http://console/overview/bank-a"), { params: Promise.resolve({ bankId: "bank-a" }) });
    const body = await response.json();
    expect(body.scan.llmFailures.coverage).toBe("unavailable");
    expect(body.pipeline.state).toBe("unknown");
  });
  it("keeps failure-page coverage visible when the latest-request source is unavailable", async () => {
    const at = new Date(Date.now() - 1000).toISOString();
    vi.stubGlobal("fetch", async (value: string) => {
      const url = new URL(value);
      if (url.pathname.endsWith("/stats")) return Response.json({ failed_consolidation: 0, pending_consolidation: 10 });
      if (url.pathname.endsWith("/operations")) return Response.json({ operations: [], total: 0 });
      if (!url.searchParams.has("status")) return new Response(null, { status: 503 });
      if (url.searchParams.get("status") === "success") return Response.json({ items: [], total: 0 });
      return Response.json({ items: [{ id: "failed-request", trace_id: "run-a", operation: "consolidation", status: "error", started_at: at, error: "ValidationError: Field required" }], total: 1 });
    });
    const response = await GET(new Request("http://console/overview/bank-a"), { params: Promise.resolve({ bankId: "bank-a" }) });
    const body = await response.json();
    expect(body.scan.llmFailures.coverage).toBe("complete");
    expect(body.lanes.find((lane: { id: string }) => lane.id === "model").state).toBe("unknown");
    expect(body.attemptHistory).toHaveLength(1);
  });
});
