type ScenarioRow = { status?: string };
type ScenarioIndex = { sessions?: ScenarioRow[]; projects?: ScenarioRow[] };

export function summarizeScenarioStatus(index: ScenarioIndex) {
  const rows = [...(index.sessions ?? []), ...(index.projects ?? [])];
  const reviewed = rows.filter((row) => row.status === "model_reviewed").length;
  const pendingReview = rows.length - reviewed;
  const qualityStatus = rows.length === 0 ? "unavailable" : pendingReview ? "unreviewed" : "reviewed";
  const pipeline = rows.length === 0
    ? "情景摘要索引不可用"
    : pendingReview
      ? "历史回填为确定性来源投影；语义归纳与来源复核尚未完成"
      : "情景摘要已完成模型复核；具体结论仍须回读原始来源";
  return { reviewed, pendingReview, qualityStatus, pipeline };
}

export function summarizeAssociationCoverage(scanned: number, liveTotal: number | null) {
  if (liveTotal == null || !Number.isFinite(liveTotal)) {
    return { liveTotal: null, unscanned: null, coverage: "unknown" as const };
  }
  const unscanned = Math.max(0, liveTotal - scanned);
  return { liveTotal, unscanned, coverage: unscanned ? "stale" as const : "current_count_only" as const };
}

export function isScenarioBankScope(selectedBank: string | null, personalBank: string) {
  return !selectedBank || selectedBank === personalBank;
}
