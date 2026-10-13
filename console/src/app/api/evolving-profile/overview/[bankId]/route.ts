import { epStatePath, EP_STATE_ROOT } from "@/lib/ep-state-paths";
import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import { buildOperationalOverview, type DispatcherActivity, type LocalRetentionEvidence, type LlmEvidence, type OperationEvidence } from "@/lib/operational-overview";
import { dataplaneBankUrl, getDataplaneHeaders } from "@/lib/evolving-client";
import { GET as getRuntime } from "@/app/api/evolving-profile/runtime/route";

const ROOT = EP_STATE_ROOT;

type BankPage = { status: "observed" | "unavailable"; items: Record<string, unknown>[]; total: number | null };
async function bankRows(bankId: string, path: string, key: "items" | "operations"): Promise<BankPage> {
  try {
    const metadataPath = key === "items" ? `${path}&include_content=false` : path;
    const response = await fetch(dataplaneBankUrl(bankId, metadataPath), {
      headers: getDataplaneHeaders(), cache: "no-store", signal: AbortSignal.timeout(2500),
    });
    if (!response.ok) return { status: "unavailable" as const, items: [], total: null };
    const body = await response.json();
    if (!Array.isArray(body[key])) return { status: "unavailable", items: [], total: null };
    // Metadata-only reads exclude prompts/outputs at the backend; project only overview evidence.
    const items = body[key].map((row: Record<string, unknown>) => key === "items" ? {
      id: row.id, operation: row.operation, scope: row.scope, trace_id: row.trace_id,
      status: row.status, started_at: row.started_at, error: row.error,
      finish_reason: (row.llm_info as Record<string, unknown> | undefined)?.finish_reason,
    } : { id: row.id, task_type: row.task_type, status: row.status, created_at: row.created_at, error_message: row.error_message,
      parent_operation_id: typeof row.parent_operation_id === "string" && row.parent_operation_id ? row.parent_operation_id : null });
    return { status: "observed", items, total: typeof body.total === "number" && body.total >= 0 ? body.total : null };
  } catch { return { status: "unavailable" as const, items: [], total: null }; }
}

async function pages(bankId: string, path: string, key: "items" | "operations", maxPages = 5): Promise<BankPage> {
  const result: BankPage = { status: "observed", items: [], total: null };
  for (let page = 0; page < maxPages; page++) {
    const row = await bankRows(bankId, `${path}&limit=100&offset=${page * 100}`, key);
    if (row.status === "unavailable") { result.status = "unavailable"; break; }
    result.items.push(...row.items); result.total = row.total;
    if (row.items.length < 100 || (result.total != null && result.items.length >= result.total)) break;
  }
  return result;
}

async function bankStats(bankId: string) {
  try {
    const response = await fetch(dataplaneBankUrl(bankId, "/stats"), { headers: getDataplaneHeaders(), cache: "no-store", signal: AbortSignal.timeout(2500) });
    if (!response.ok) throw new Error("stats_unavailable");
    const body = await response.json();
    if (![body.failed_consolidation, body.pending_consolidation].every((count) => Number.isInteger(count) && count >= 0)) throw new Error("invalid_stats");
    return { status: "observed" as const, failed_consolidation: body.failed_consolidation as number, pending_consolidation: body.pending_consolidation as number, operations_by_status: body.operations_by_status as Record<string, number> | undefined };
  } catch { return { status: "unavailable" as const }; }
}

async function relatedSuccesses(bankId: string, items: Record<string, unknown>[], start: string, end: string) {
  const traces = [...new Set(items.flatMap((row) => typeof row.trace_id === "string" && row.trace_id ? [row.trace_id] : []))];
  const checked: string[] = []; const successes: Record<string, unknown>[] = [];
  let unavailable = false;
  // Bound trace fanout and concurrency as well as per-trace paging.
  const selected = traces.slice(0, 50);
  for (let index = 0; index < selected.length; index += 5) {
    const batch = await Promise.all(selected.slice(index, index + 5).map(async (trace) => ({ trace,
      rows: await pages(bankId, `/llm-requests?status=success&trace_id=${encodeURIComponent(trace)}&start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}`, "items", 2) })));
    for (const { trace, rows } of batch) {
      successes.push(...rows.items);
      if (rows.status === "observed" && rows.total != null && rows.items.length >= rows.total) checked.push(trace);
      else unavailable ||= rows.status === "unavailable";
    }
  }
  return { items: successes, checked, status: unavailable && !checked.length ? "unavailable" as const : checked.length < traces.length ? "partial" as const : "observed" as const };
}

async function backupEvents() {
  try {
    const content = await readFile(`${ROOT}/logs/backup-run-receipts.jsonl`, "utf8");
    return content.split("\n").slice(-500).flatMap((line) => {
      try {
        const row = JSON.parse(line);
        return row.at && row.status && row.code ? [{ at: row.at, status: row.status, code: row.code, detail: String(row.detail ?? row.code) }] : [];
      } catch { return []; }
    });
  } catch { return []; }
}

async function mapStatus() {
  try {
    const structural = JSON.parse(await readFile(`${ROOT}/catalog/topics.refresh.json`, "utf8"));
    try {
      const semantic = JSON.parse(await readFile(`${ROOT}/catalog/corpus-navigation.status.json`, "utf8").catch(() => readFile(`${ROOT}/catalog/semantic-topics.status.json`, "utf8")));
      return { ...structural, semantic_worker_status: semantic.status, semantic_error_type: semantic.error_type };
    } catch { return { ...structural, semantic_worker_status: "unknown" }; }
  }
  catch { return { status: "unknown" }; }
}

async function localRetentionStatus(bankId: string, now: number): Promise<LocalRetentionEvidence> {
  const empty: LocalRetentionEvidence = { status: "unavailable", observedAt: null, quarantinedRecords: null, inflightRecords: null, heldRecords: null, pendingRecords: null,
    quarantineBatches: [], dispatcher: { status: "unavailable", activity: "unknown", at: null } };
  const activity: Record<string, DispatcherActivity> = { idle: "idle", processing: "processing", submitting: "submitting", submitted: "processing", recovered_acknowledgement: "processing",
    retry_requested: "retrying", retry_pending: "retrying", retry_quarantined: "isolated", retry_policy_held: "isolated", intent_policy_held: "isolated", disabled: "disabled",
    worker_error: "error", status_unavailable: "error", retry_unavailable: "error", acknowledgement_conflict: "error", intent_conflict: "error" };
  const [queue, dispatcher] = await Promise.all([
    (async () => {
      try {
        // Configuration is read solely to resolve the same local queue as the worker.
        let queuePath = epStatePath("codex/state/retention-queue.json");
        for (const configPath of [epStatePath("codex/settings.json"), epStatePath("codex.json")]) {
          try {
            const config = JSON.parse(await readFile(configPath, "utf8"));
            if (!config || typeof config !== "object" || Array.isArray(config)) throw new Error("invalid_config");
            if (config.retainQueuePath != null) {
              if (typeof config.retainQueuePath !== "string" || !config.retainQueuePath.trim()) throw new Error("invalid_queue_path");
              queuePath = config.retainQueuePath;
            }
          } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
        }
        const body = JSON.parse(await readFile(queuePath, "utf8"));
        if (!Array.isArray(body.items) || body.items.some((row: unknown) => !row || typeof row !== "object" || Array.isArray(row) || typeof (row as Record<string, unknown>).bank_id !== "string" || !(row as Record<string, unknown>).bank_id)) throw new Error("invalid_queue");
        const rows = body.items.filter((row: Record<string, unknown>) => row.bank_id === bankId);
        const batches = new Map<string, { operationId: string; count: number; at: string | null }>();
        let quarantinedRecords = 0, inflightRecords = 0, heldRecords = 0, pendingRecords = 0;
        for (const row of rows) {
          if (row.operation_id != null && (typeof row.operation_id !== "string" || !row.operation_id)) throw new Error("invalid_operation_binding");
          if (row.retention_origin_hold != null && typeof row.retention_origin_hold !== "string") throw new Error("invalid_origin_hold");
          if (row.retention_quarantine) {
            const hold = row.retention_quarantine;
            if (typeof hold !== "object" || Array.isArray(hold) || typeof hold.operation_id !== "string" || !hold.operation_id) throw new Error("invalid_quarantine");
            quarantinedRecords++;
            const at = typeof hold.at === "string" && Number.isFinite(Date.parse(hold.at)) ? hold.at : null;
            const batch = batches.get(hold.operation_id) ?? { operationId: hold.operation_id, count: 0, at };
            batch.count++;
            if (at && (!batch.at || Date.parse(at) > Date.parse(batch.at))) batch.at = at;
            batches.set(hold.operation_id, batch);
          }
          if (row.operation_id) inflightRecords++;
          if (row.retention_origin_hold) heldRecords++;
          if (!row.operation_id && !row.retention_origin_hold && !row.retention_quarantine) pendingRecords++;
        }
        return { status: "observed" as const, observedAt: new Date(now).toISOString(), quarantinedRecords, inflightRecords, heldRecords, pendingRecords, quarantineBatches: [...batches.values()] };
      } catch { return empty; }
    })(),
    (async (): Promise<LocalRetentionEvidence["dispatcher"]> => {
      try {
        const row = JSON.parse(await readFile(epStatePath("retention/worker-state.json"), "utf8"));
        const at = typeof row.at === "string" ? row.at : null;
        const age = now - Date.parse(at ?? "");
        if (!Number.isFinite(age) || age < 0) return empty.dispatcher;
        // The receipt describes the host worker, never per-Bank queue counts.
        return { status: age > 180_000 ? "stale" : "observed", activity: activity[row.status] ?? "unknown", at };
      } catch { return empty.dispatcher; }
    })(),
  ]);
  return { ...queue, dispatcher };
}

export async function GET(_request: Request, { params }: { params: Promise<{ bankId: string }> }) {
  const { bankId } = await params;
  if (!bankId) return NextResponse.json({ error: "bank_id is required" }, { status: 400 });
  const now = Date.now();
  const start = new Date(now - 24 * 60 * 60 * 1000).toISOString();
  const end = new Date(now + 1).toISOString();
  const failurePath = `/llm-requests?status=error&start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}`;
  const [runtimeResponse, llmFailures, failureGroups, latestRequest, failedOps, recentRetain, stats, events, map, localRetention] = await Promise.all([
    getRuntime(),
    pages(bankId, failurePath, "items"),
    bankRows(bankId, `${failurePath}&group=true&count_only=true&limit=1`, "items"),
    bankRows(bankId, `/llm-requests?start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}&limit=1`, "items"),
    pages(bankId, "/operations?status=failed", "operations"),
    bankRows(bankId, "/operations?type=retain&status=completed&limit=1", "operations"),
    bankStats(bankId),
    backupEvents(), mapStatus(), localRetentionStatus(bankId, now),
  ]);
  const runtime = await runtimeResponse.json();
  const related = await relatedSuccesses(bankId, llmFailures.items, start, end);
  const llm = { status: llmFailures.status, currentStatus: latestRequest.status,
    items: [...llmFailures.items, ...latestRequest.items, ...related.items] as LlmEvidence[], total: llmFailures.total, groupTotal: failureGroups.total,
    relatedSuccessStatus: related.status, relatedTracesChecked: related.checked };
  const operations = { status: failedOps.status === "observed" && recentRetain.status === "observed" ? "observed" as const : "unavailable" as const,
    items: [...failedOps.items, ...recentRetain.items] as OperationEvidence[], total: failedOps.total, returned: failedOps.items.length };
  const result = buildOperationalOverview({ now, runtime, backupEvents: events, llm, operations, bankStats: stats, map, localRetention });
  return NextResponse.json({ ...result, bankId },
    { headers: { "Cache-Control": "no-store" } });
}
