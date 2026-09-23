import type { FusionModel, PreferenceDimension, PreferenceUnit } from "@/lib/preference-graph";

export type PreferenceSelection = PreferenceDimension | "fusion" | "all";
export type PreferenceLifecycle = "approved" | "needs_review" | "superseded" | "all";

export type PreferenceTableRow =
  | { id: string; kind: "preference"; title: string; lifecycle: string; at: number; unit: PreferenceUnit }
  | { id: string; kind: "model"; title: string; lifecycle: string; at: number; model: FusionModel };

function asEpoch(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value > 1_000_000_000_000 ? value : value * 1000;
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  return 0;
}

export function visiblePreferenceUnits(
  units: PreferenceUnit[],
  selection: PreferenceSelection,
  lifecycle: PreferenceLifecycle = "all"
): PreferenceUnit[] {
  return units.filter((unit) =>
    (selection === "all" || (selection !== "fusion" && unit.primary_category === selection)) &&
    (lifecycle === "all" || unit.preference_audit?.state === lifecycle)
  );
}

export function preferenceTableRows(
  units: PreferenceUnit[],
  models: FusionModel[],
  selection: PreferenceSelection,
  lifecycle: PreferenceLifecycle = "all"
): PreferenceTableRow[] {
  const unitRows: PreferenceTableRow[] = visiblePreferenceUnits(units, selection, lifecycle).map((unit) => ({
    id: unit.id,
    kind: "preference",
    title: unit.text,
    lifecycle: unit.preference_audit?.state ?? "not_reviewed",
    at: asEpoch(unit.activated_at),
    unit,
  }));
  const modelRows: PreferenceTableRow[] = (lifecycle === "needs_review" || lifecycle === "superseded" ? [] : selection === "all" || selection === "fusion" ? models : []).map((model) => ({
    id: model.id,
    kind: "model",
    title: model.title,
    lifecycle: model.status ?? "active",
    at: asEpoch(model.last_verified_at),
    model,
  }));
  return [...unitRows, ...modelRows];
}

export function preferenceTimelineEvents(
  units: PreferenceUnit[],
  models: FusionModel[],
  selection: PreferenceSelection,
  lifecycle: PreferenceLifecycle = "all"
): PreferenceTableRow[] {
  return preferenceTableRows(units, models, selection, lifecycle).sort((left, right) => right.at - left.at);
}
