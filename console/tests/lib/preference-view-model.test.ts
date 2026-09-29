import { describe, expect, it } from "vitest";
import {
  preferenceTableRows,
  preferenceTimelineEvents,
  visiblePreferenceUnits,
} from "@/lib/preference-view-model";
import type { FusionModel, PreferenceUnit } from "@/lib/preference-graph";

const units: PreferenceUnit[] = [
  {
    id: "u-approved",
    primary_category: "reasoning",
    text: "Use evidence.",
    activated_at: 20,
    preference_audit: { state: "approved" },
  },
  {
    id: "u-review",
    primary_category: "delivery",
    text: "Review the output.",
    activated_at: 10,
    preference_audit: { state: "needs_review" },
  },
];

const models: FusionModel[] = [{
  id: "m-1",
  title: "Evidence delivery",
  dimensions: ["reasoning", "delivery"],
  last_verified_at: "2026-09-17T12:00:00Z",
}];

describe("preference view model", () => {
  it("keeps a dimension view limited to its own preference units", () => {
    expect(visiblePreferenceUnits(units, "reasoning").map((unit) => unit.id)).toEqual(["u-approved"]);
    expect(visiblePreferenceUnits(units, "fusion")).toEqual([]);
  });

  it("keeps review and superseded items out of the default published view", () => {
    expect(visiblePreferenceUnits(units, "all", "approved").map((unit) => unit.id)).toEqual(["u-approved"]);
  });

  it("keeps lifecycle state in table rows instead of silently treating review items as published", () => {
    expect(preferenceTableRows(units, models, "all")).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "u-approved", kind: "preference", lifecycle: "approved" }),
      expect.objectContaining({ id: "u-review", kind: "preference", lifecycle: "needs_review" }),
      expect.objectContaining({ id: "m-1", kind: "model", lifecycle: "active" }),
    ]));
  });

  it("orders timeline events by their actual event time", () => {
    expect(preferenceTimelineEvents(units, models, "all").map((event) => event.id)).toEqual([
      "m-1",
      "u-approved",
      "u-review",
    ]);
  });
});
