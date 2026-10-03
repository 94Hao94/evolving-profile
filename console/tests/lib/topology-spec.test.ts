import { describe, expect, it } from "vitest";
import { buildTopologySpec, type TopologyBranchSummary } from "@/lib/topology-spec";

const branch = (candidates: number, returned: number, delivered: number, text: string): TopologyBranchSummary => ({
  status: delivered ? "delivered" : returned ? "candidate_returned" : "not_observed",
  counts: { candidates, returned, delivered, tokens: 0 },
  receipts: [],
  items: text ? [{ kind: "test", text }] : [],
});

describe("topology branch receipt projection", () => {
  it("keeps user branches independent and aggregates them at the parent", () => {
    const branches = new Map([
      ["user-memory-recall", branch(2, 2, 2, "recall item")],
      ["user-memory-research", branch(4, 1, 1, "research item")],
      ["user-memory-scenario-summary", branch(1, 1, 0, "scenario locator")],
      ["user-memory-read-source", branch(0, 0, 0, "")],
    ]);
    const result = buildTopologySpec({
      english: true,
      sourceScope: "prompt_bound",
      summaries: new Map(),
      guidanceItems: [{ kind: "Preference", text: "preference" }],
      branchSummaries: branches,
    });
    const node = (id: string) => result.nodes.find((item) => item.id === id)!;
    expect(node("user-memory-recall").data.counts).toMatchObject({ candidates: 2, returned: 2, delivered: 2 });
    expect(node("user-memory-research").data.counts).toMatchObject({ candidates: 4, returned: 1, delivered: 1 });
    expect(node("user-memory-scenario-summary").data.counts).toMatchObject({ candidates: 1, returned: 1, delivered: 0 });
    expect(node("user-memory-read-source").data.counts).toMatchObject({ candidates: 0, returned: 0, delivered: 0 });
    expect(node("user-root").data.counts).toMatchObject({ candidates: 8, returned: 5, delivered: 4 });
    expect(node("user-memory-research").data.items).toEqual([{ kind: "test", text: "research item" }]);
  });

  it("does not copy an aggregate Agent lane count into every child", () => {
    const branches = new Map([
      ["agent-process-memory-observe-trajectory", branch(0, 0, 0, "")],
      ["agent-process-memory-process-retrieval", branch(3, 3, 3, "retrieved process" )],
      ["agent-process-memory-compatibility-gate", branch(1, 1, 0, "gate result")],
      ["agent-process-memory-guidance", branch(0, 0, 0, "")],
    ]);
    const result = buildTopologySpec({ english: true, sourceScope: "prompt_bound", summaries: new Map([[
      "agent_process", { lane: "agent_process", status: "delivered", receipts: [], counts: { candidates: 4, returned: 4, delivered: 3, tokens: 0 } },
    ]]), branchSummaries: branches });
    const node = (id: string) => result.nodes.find((item) => item.id === id)!;
    expect(node("agent-process-memory-process-retrieval").data.counts.delivered).toBe(3);
    expect(node("agent-process-memory-compatibility-gate").data.counts.delivered).toBe(0);
    expect(node("agent-process-memory-observe-trajectory").data.counts.candidates).toBe(0);
    expect(node("agent-root").data.counts).toMatchObject({ candidates: 4, returned: 4, delivered: 3 });
  });
});
