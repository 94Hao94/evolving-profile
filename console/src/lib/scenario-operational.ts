import type { ScenarioSnapshot } from "./scenario-data";
import { projectSessionContextNode } from "./context-node";

export type ScenarioOperationalEvidence = {
  status: "observed" | "unavailable"; at: string | null;
  total: number | null; reviewed: number | null; failed: number | null;
  pending: number | null; notApplicable: number | null; protected: number | null;
  waitingSource: number | null; unknown: number | null;
  failures: Array<{ id: string; code: string }>;
};
export function scenarioOperationalEvidence(snapshot: ScenarioSnapshot | null): ScenarioOperationalEvidence {
  const empty: ScenarioOperationalEvidence = { status: "unavailable", at: null, total: null, reviewed: null, failed: null, pending: null, notApplicable: null, protected: null, waitingSource: null, unknown: null, failures: [] };
  if (!snapshot || snapshot.index.status === "unavailable" || !Array.isArray(snapshot.index.sessions)) return empty;
  const rows = snapshot.index.sessions;
  if (rows.some(row => !row || typeof row !== "object" || (row.bank_id && row.bank_id !== snapshot.bankId))) return empty;
  const value = { ...empty, status: "observed" as const, at: typeof snapshot.index.updated_at === "string" ? snapshot.index.updated_at : null,
    total: rows.length, reviewed: 0, failed: 0, pending: 0, notApplicable: 0, protected: 0, waitingSource: 0, unknown: 0 };
  for (const row of rows) {
    switch (row.status) {
      case "model_reviewed": case "episode_directory_ready":
        if (projectSessionContextNode(row as any).automatedSourceCoverage?.status === "reviewed") value.reviewed++;
        else if (row.status === "episode_directory_ready") value.pending++;
        else value.unknown++;
        break;
      case "raw_available_summary_failed":
        value.failed++;
        if (typeof row.context_id === "string") value.failures.push({ id: row.context_id, code: typeof row.error_code === "string" ? row.error_code.slice(0, 160) : "unknown" });
        break;
      case "raw_available_summary_source_not_applicable": value.notApplicable++; break;
      case "raw_available_summary_protected": value.protected++; break;
      case "raw_available_summary_waiting_source": value.waitingSource++; break;
      case "raw_available_summary_pending": case "deterministic_projection_unreviewed": value.pending++; break;
      default: value.unknown++;
    }
  }
  return value;
}
