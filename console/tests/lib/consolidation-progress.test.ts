import { describe, expect, it } from "vitest";
import { consolidationProgress, sourceConsolidationProgress } from "../../src/lib/consolidation-progress";

describe("consolidation progress", () => {
  it("never counts derived observations as successfully consolidated sources", () => {
    expect(sourceConsolidationProgress({nodes_by_fact_type:{world:10, experience:0, observation:100},pending_consolidation:10,failed_consolidation:0})).toEqual({total:10,done:0,percent:0});
  });
  it("never counts failed source memories as completed", () => {
    expect(consolidationProgress(63239, 0, 6)).toEqual({done:63233, percent:99.9});
  });
  it("keeps both pending and failed work out of successful count", () => {
    expect(consolidationProgress(100, 20, 5)).toEqual({done:75, percent:75});
  });
  it("only reports 100 when nothing remains", () => {
    expect(consolidationProgress(100, 0, 0)).toEqual({done:100, percent:100});
    expect(consolidationProgress(0, 0, 0)).toEqual({done:0, percent:0});
  });
  it("does not show negative progress for inconsistent snapshots", () => {
    expect(consolidationProgress(3, 2, 4)).toEqual({done:0, percent:0});
  });
});
