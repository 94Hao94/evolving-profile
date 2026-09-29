export type ManualSourceCoverage = {
  scopeVerdict?: string;
  reviewedSourceMessageCount?: number;
  episodeScopeVerdict?: string;
};

const EPISODE_SCOPE_LABELS: Record<string, string> = {
  single_coherent_task: "单一连贯任务",
  multiple_topics: "多主题，需拆分",
  uncertain: "范围未决",
  unresolved: "范围未决",
};

export function describeManualSourceCoverage(
  coverage?: ManualSourceCoverage,
  sourceMessageCount?: number,
): string | null {
  if (!coverage) return null;
  const parts: string[] = [];
  if (coverage.scopeVerdict === "whole_session_scope_acceptable") {
    parts.push("全会话已复核");
  } else if (coverage.scopeVerdict) {
    parts.push("范围复核");
  }
  if (typeof coverage.reviewedSourceMessageCount === "number") {
    const total = typeof sourceMessageCount === "number" ? sourceMessageCount : "?";
    parts.push(`${coverage.reviewedSourceMessageCount}/${total} 条消息`);
  }
  if (coverage.episodeScopeVerdict) {
    parts.push(EPISODE_SCOPE_LABELS[coverage.episodeScopeVerdict] ?? "待核实");
  }
  return parts.length ? parts.join(" · ") : null;
}

type SessionContextRecord = {
  context_id: string;
  session_id: string;
  project_key?: string;
  status?: string;
  review_scope?: string;
  raw_source_files?: string[];
  source_message_count?: number;
  manual_source_coverage?: {
    scope_verdict?: string;
    reviewed_source_message_count?: number;
    episode_scope_verdict?: string;
  } | null;
  summary?: Record<string, string>;
  summary_budget?: Record<string, { truncated?: boolean; source_already_truncated?: boolean }>;
  source_ids?: string[];
};

export function projectSessionContextNode(row: SessionContextRecord) {
  const coverage = row.manual_source_coverage;
  return {
    id: row.context_id,
    type: "session" as const,
    label: row.session_id,
    projectKey: row.project_key,
    status: row.status,
    reviewScope: row.review_scope,
    rawSourceCount: (row.raw_source_files ?? []).length,
    sourceMessageCount: row.source_message_count,
    manualSourceCoverage: coverage
      ? {
          scopeVerdict: coverage.scope_verdict,
          reviewedSourceMessageCount: coverage.reviewed_source_message_count,
          episodeScopeVerdict: coverage.episode_scope_verdict,
        }
      : undefined,
    summary: row.summary ?? {},
    summaryBudget: row.summary_budget ?? {},
    sourceIds: row.source_ids ?? [],
  };
}
