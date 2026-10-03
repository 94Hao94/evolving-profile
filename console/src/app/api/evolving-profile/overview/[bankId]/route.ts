import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { homedir } from "node:os";
import { buildOperationalOverview } from "@/lib/operational-overview";
import { dataplaneBankUrl, getDataplaneHeaders } from "@/lib/evolving-client";
import { GET as getRuntime } from "@/app/api/evolving-profile/runtime/route";

const ROOT = process.env.EVOLVING_PROFILE_STATE_ROOT ?? path.join(homedir(), ".evolving-profile");

async function bankRows(bankId: string, path: string, key: "items" | "operations") {
  try {
    const response = await fetch(dataplaneBankUrl(bankId, path), {
      headers: getDataplaneHeaders(), cache: "no-store", signal: AbortSignal.timeout(2500),
    });
    if (!response.ok) return { status: "unavailable" as const, items: [], total: null };
    const body = await response.json();
    return { status: "observed" as const, items: Array.isArray(body[key]) ? body[key] : [], total: body.total ?? null };
  } catch { return { status: "unavailable" as const, items: [], total: null }; }
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

export async function GET(_request: Request, { params }: { params: Promise<{ bankId: string }> }) {
  const { bankId } = await params;
  if (!bankId) return NextResponse.json({ error: "bank_id is required" }, { status: 400 });
  const start = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const [runtimeResponse, llmFailures, lastSuccess, failedOps, recentRetain, events, map] = await Promise.all([
    getRuntime(),
    bankRows(bankId, `/llm-requests?status=error&start_date=${encodeURIComponent(start)}&limit=100`, "items"),
    bankRows(bankId, "/llm-requests?status=success&limit=1", "items"),
    bankRows(bankId, "/operations?status=failed&limit=100", "operations"),
    bankRows(bankId, "/operations?type=retain&status=completed&limit=1", "operations"),
    backupEvents(), mapStatus(),
  ]);
  const runtime = await runtimeResponse.json();
  const llm = { status: llmFailures.status === "observed" && lastSuccess.status === "observed" ? "observed" as const : "unavailable" as const,
    items: [...llmFailures.items, ...lastSuccess.items] };
  const operations = { status: failedOps.status === "observed" && recentRetain.status === "observed" ? "observed" as const : "unavailable" as const,
    items: [...failedOps.items, ...recentRetain.items] };
  const result = buildOperationalOverview({ now: Date.now(), runtime, backupEvents: events, llm, operations, map });
  return NextResponse.json({ ...result, bankId,
    scan: { llmFailures: { returned: llmFailures.items.length, total: llmFailures.total }, failedOperations: { returned: failedOps.items.length, total: failedOps.total } } },
    { headers: { "Cache-Control": "no-store" } });
}
