import { describe, expect, it } from "vitest";
import {
  buildPreferenceGraph,
  FUSION_MODEL_COLOR,
  preferenceDimensionColor,
  type FusionModel,
  type PreferenceUnit,
} from "@/lib/preference-graph";

const units: PreferenceUnit[] = [
  { id: "communication-1", primary_category: "communication", text: "Use a clear conclusion first." },
  { id: "learning-1", primary_category: "learning", text: "Use examples for difficult ideas." },
];

const models: FusionModel[] = [
  {
    id: "model-1",
    title: "Evidence-first delivery",
    dimensions: ["communication", "learning"],
    sections: [{ guidance_refs: [{ id: "communication-1" }, { id: "learning-1" }] }],
  },
];

describe("buildPreferenceGraph", () => {
  it("uses a fusion color that is distinct from all five preference dimensions", () => {
    expect(FUSION_MODEL_COLOR).toMatch(/^#[0-9a-f]{6}$/i);
    expect(FUSION_MODEL_COLOR).not.toBe(preferenceDimensionColor("reasoning"));
    expect(FUSION_MODEL_COLOR).not.toBe(preferenceDimensionColor("delivery"));
  });

  it("keeps a selected preference dimension isolated from fusion models", () => {
    const graph = buildPreferenceGraph(units, models, "communication");

    expect(graph.nodes.map((node) => node.id)).toEqual([
      "dimension:communication",
      "communication-1",
    ]);
    expect(graph.links).toHaveLength(1);
  });

  it("keeps the fusion model view separate from the five preference dimensions", () => {
    const graph = buildPreferenceGraph(units, models, "fusion");

    expect(graph.nodes.map((node) => node.id)).toContain("fusion-center");
    expect(graph.nodes.map((node) => node.id)).toContain("model:model-1");
    expect(graph.nodes.map((node) => node.id)).not.toContain("communication-1");
    expect(graph.nodes.map((node) => node.id)).not.toContain("learning-1");
  });

  it("shows all five dimensions plus fusion in the default overview", () => {
    const graph = buildPreferenceGraph(units, models, "all");

    expect(graph.nodes.map((node) => node.id)).toEqual(expect.arrayContaining([
      "dimension:communication",
      "dimension:learning",
      "dimension:reasoning",
      "dimension:collaboration",
      "dimension:delivery",
      "fusion-center",
      "model:model-1",
      "communication-1",
      "learning-1",
    ]));
  });
});
