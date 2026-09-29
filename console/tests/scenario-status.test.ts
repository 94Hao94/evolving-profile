import { describe, expect, it } from "vitest";
import { isScenarioBankScope, summarizeAssociationCoverage, summarizeScenarioStatus } from "../src/lib/scenario-status";

describe("summarizeScenarioStatus", () => {
  it("does not portray deterministic projections as model reviewed", () => {
    const value = summarizeScenarioStatus({
      sessions: [{ status: "direct_agent_processed" }],
      projects: [{ status: "deterministic_projection_unreviewed" }],
    });
    expect(value.pendingReview).toBe(2);
    expect(value.reviewed).toBe(0);
    expect(value.qualityStatus).toBe("unreviewed");
    expect(value.pipeline).toContain("确定性来源投影");
    expect(value.pipeline).not.toContain("Luna");
  });

  it("only reports reviewed when all available summaries were reviewed", () => {
    const value = summarizeScenarioStatus({
      sessions: [{ status: "model_reviewed" }], projects: [{ status: "model_reviewed" }],
    });
    expect(value.pendingReview).toBe(0);
    expect(value.reviewed).toBe(2);
    expect(value.qualityStatus).toBe("reviewed");
  });
});

describe("summarizeAssociationCoverage", () => {
  it("reports records created after the association snapshot", () => {
    expect(summarizeAssociationCoverage(49017, 49103)).toEqual({
      liveTotal: 49103, unscanned: 86, coverage: "stale",
    });
  });

  it("keeps coverage unknown when the live bank is unavailable", () => {
    expect(summarizeAssociationCoverage(49017, null).coverage).toBe("unknown");
  });
});

describe("isScenarioBankScope", () => {
  it("does not reuse the personal scenario index on another bank page", () => {
    expect(isScenarioBankScope("other-agent-bank", "personal-bank")).toBe(false);
    expect(isScenarioBankScope("personal-bank", "personal-bank")).toBe(true);
  });
});
