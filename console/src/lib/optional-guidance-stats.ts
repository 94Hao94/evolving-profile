/** Optional guidance failures must not suppress real Bank statistics or become zero. */
export type OptionalGuidanceStats = {
  models: { active: number | null; candidates: number | null; archived: number | null };
  readiness: { total: number | null; states: Record<string, number> };
};
const count = (value: unknown): number | null => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
async function optionalJson(url: string): Promise<any> {
  try {
    const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(3000) });
    if (!response.ok) return null;
    return await response.json();
  } catch { return null; }
}
export async function loadGuidanceStats(): Promise<OptionalGuidanceStats> {
  const [models, candidates] = await Promise.all([
    optionalJson("/api/evolving-profile/guidance/models"),
    optionalJson("/api/evolving-profile/guidance/candidates?limit=500"),
  ]);
  const states: Record<string, number> = Object.create(null);
  if (Array.isArray(candidates?.items)) {
    for (const item of candidates.items) {
      const state = typeof item?.state === "string" ? item.state : "unknown";
      states[state] = (states[state] ?? 0) + 1;
    }
  }
  return {
    models: { active: count(models?.counts?.active), candidates: count(models?.counts?.candidates), archived: count(models?.counts?.archived_legacy) },
    readiness: { total: count(candidates?.total), states },
  };
}
