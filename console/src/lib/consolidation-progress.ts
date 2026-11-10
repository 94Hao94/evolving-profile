/** Successful processing excludes both queued and permanently failed sources. */
export function consolidationProgress(total: number, pending: number, failed: number) {
  const done = Math.max(0, total - pending - failed);
  const percent = total <= 0 ? 0 : done >= total ? 100 : Math.floor(done / total * 1000) / 10;
  return { done, percent };
}

export function sourceConsolidationProgress(stats: {nodes_by_fact_type: Record<string, number | undefined>;pending_consolidation:number;failed_consolidation?:number}) {
  const total=(stats.nodes_by_fact_type.world ?? 0)+(stats.nodes_by_fact_type.experience ?? 0);
  return {total,...consolidationProgress(total,stats.pending_consolidation,stats.failed_consolidation ?? 0)};
}
