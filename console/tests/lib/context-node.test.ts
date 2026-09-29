import { describe, expect, it } from "vitest";
import { describeManualSourceCoverage, projectSessionContextNode } from "@/lib/context-node";

describe("projectSessionContextNode", () => {
  it("exposes reviewed message coverage and task-scope verdict", () => {
    const node = projectSessionContextNode({
      context_id: "session:thread-1",
      session_id: "thread-1",
      project_key: "project-1",
      status: "model_reviewed",
      review_scope: "conversation_only_not_external_fact_verification",
      raw_source_files: ["/rollouts/thread-1.jsonl"],
      source_message_count: 160,
      manual_source_coverage: {
        scope_verdict: "whole_session_scope_acceptable",
        reviewed_source_message_count: 160,
        episode_scope_verdict: "single_coherent_task",
      },
    });

    expect(node).toMatchObject({
      id: "session:thread-1",
      type: "session",
      sourceMessageCount: 160,
      manualSourceCoverage: {
        scopeVerdict: "whole_session_scope_acceptable",
        reviewedSourceMessageCount: 160,
        episodeScopeVerdict: "single_coherent_task",
      },
    });
  });
});

describe("describeManualSourceCoverage", () => {
  it("keeps explicit zero counts visible", () => {
    expect(describeManualSourceCoverage({
      scopeVerdict: "whole_session_scope_acceptable",
      reviewedSourceMessageCount: 0,
      episodeScopeVerdict: "single_coherent_task",
    }, 0)).toBe("全会话已复核 · 0/0 条消息 · 单一连贯任务");
  });

  it("does not invent a review state for legacy rows without coverage", () => {
    expect(describeManualSourceCoverage(undefined, 160)).toBeNull();
  });
});
