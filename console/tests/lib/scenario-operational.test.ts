import { describe, expect, it } from "vitest";
import { scenarioOperationalEvidence } from "@/lib/scenario-operational";
import { buildOperationalOverview, acknowledgeOperationalLane, parseOperationalAcknowledgements, isOperationalLaneAcknowledged } from "@/lib/operational-overview";

describe("scenario operational evidence", () => {
  it.each(["model_reviewed", "episode_directory_ready"])("separates source-reviewed %s from failed, pending and ineligible sessions", status => {
    const view = scenarioOperationalEvidence({ bankId: "a", index: { status: "ready", updated_at: "2026-10-15T06:00:00Z", sessions: [
      { context_id: "session:one", bank_id: "a", status, source_revision: "revision-a", source_message_count: 1,
        automated_source_coverage: { accept: true, whole_source_topics_covered: true, corrections_preserved: true, assistant_claims_labeled: true, partition_exact: true,
          source_revision: "revision-a", reviewed_message_ids: ["message-a"], coverage_protocol: "per_user_source_to_state_and_summary.v2",
          model_review_receipt: { source_revision: "revision-a", input_clipped: false, host_validation_version: "source-coverage-primary-context.v3" } }, summary: { full: "PRIVATE SOURCE" } },
      { context_id: "session:two", bank_id: "a", status: "raw_available_summary_failed", error_code: "source_quote_invalid", raw_source_files: ["PRIVATE PATH"] },
      { context_id: "session:three", bank_id: "a", status: "raw_available_summary_pending" },
      { context_id: "session:four", bank_id: "a", status: "raw_available_summary_source_not_applicable" },
      { context_id: "session:five", bank_id: "a", status: "raw_available_summary_protected" },
    ] } } as any);
    expect(view).toMatchObject({ status: "observed", total: 5, reviewed: 1, failed: 1, pending: 1, notApplicable: 1, protected: 1, unknown: 0 });
    expect(view.failures).toEqual([{ id: "session:two", code: "source_quote_invalid" }]);
    expect(JSON.stringify(view)).not.toContain("PRIVATE");
  });
  it("never converts an unreadable or foreign-Bank source into zero failures", () => {
    expect(scenarioOperationalEvidence(null).status).toBe("unavailable");
    const view = scenarioOperationalEvidence({ bankId: "a", index: { status: "ready", sessions: [{ bank_id: "b", status: "model_reviewed" }] } } as any);
    expect(view).toMatchObject({ status: "unavailable", failed: null });
  });
  it("does not certify an old status label without current complete source review", () => {
    const view = scenarioOperationalEvidence({ bankId: "a", index: { status: "ready", sessions: [{ context_id: "session:old", status: "model_reviewed", source_revision: "new",
      automated_source_coverage: { accept: false, source_revision: "old" } }] } } as any);
    expect(view).toMatchObject({ reviewed: 0, unknown: 1 });
  });
  it("does not let healthy source consolidation hide failing scenario summaries", () => {
    const result = buildOperationalOverview({ now: Date.now(), runtime: { services: [] }, backupEvents: [], llm: { status: "observed", items: [] },
      operations: { status: "observed", items: [] }, map: { status: "ready" }, bankStats: { status: "observed", failed_consolidation: 0, pending_consolidation: 0 },
      scenario: { status: "observed", at: null, total: 5, reviewed: 1, failed: 3, pending: 1, notApplicable: 0, protected: 0, waitingSource: 0, unknown: 0,
        failures: [{ id: "session:two", code: "quote_invalid" }] } } as any);
    expect(result.lanes.find(x => x.id === "scenario")).toMatchObject({ state: "critical" });
    expect(result.incidents.find(x => x.id === "scenario:failed")).toMatchObject({ count: 3, action: "scenario" });
    expect(result.pipeline.scenario?.failed).toBe(3);
    const lane = result.lanes.find(x => x.id === "scenario")!;
    const acknowledgement = acknowledgeOperationalLane({}, lane, result.incidents, []);
    const restored = parseOperationalAcknowledgements(JSON.stringify(acknowledgement));
    expect(isOperationalLaneAcknowledged(lane, result.incidents, [], restored)).toBe(true);
    const changed = result.incidents.map(x => x.id === "scenario:failed" ? { ...x, sourceIds: ["session:new-failure"] } : x);
    expect(isOperationalLaneAcknowledged(lane, changed, [], restored)).toBe(false);
  });
});
