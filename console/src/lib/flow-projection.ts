export type FlowEvidenceItem = {
  id: string;
  type?: string;
  text?: string;
  score?: number;
  title?: string;
};

export type FlowPrompt = {
  prompt_id: string;
  at: string;
  user_prompt: string;
  source?: string;
  task_state?: { current_objective?:string; current_message?:string; continuation?:boolean; continuation_context?:string|null; source?:string; authority?:string } | null;
  evidence_decision?: { need?:string; known_from_current_context?:boolean; unresolved_slots?:string[]; chosen_route?:string; sufficiency?:string; conflicts?:string[]; source_ids?:string[]; next_action?:string|null; stop_reason?:string|null; boundary?:string } | null;
  history_decision?: "needed" | "not_needed" | "unknown" | "agent_decides";
  history_decision_evidence?: string;
  memory_route_receipt?: {
    decision?: string;
    recommended_route?: string;
    reason?: string;
    confidence?: number;
    confidence_semantics?: string;
    matched_nodes?: string[];
    catalog_probe?: { status?: string; candidate_count?: number | null; matched_entities?: string[]; catalog_coverage?: string };
    catalog_hints?: Array<{ topic_id?: string; title?: string; abstract?: string; overview?: string; entities?: string[]; time_range?: {start?:string|null;end?:string|null}; source_count?:number; source_count_semantics?:string; coverage?:{sampled?:number;total?:number|null;semantics?:string}; pending_changes?:number|null; conflicts?:string[]|null; pending_changes_status?:string; conflict_status?:string; content_status?:string; refreshed_at?:string|null; boundary?:string; memory_id?: string; type?: string; topic?: string; mentioned_at?: string | null; occurred_start?: string | null; occurred_end?: string | null; state?: string }>;
    agent_may_override?: boolean;
    tool_events?: Array<{ tool?: string; at?: string; route?: string; research_id?: string | null; query?: string | null; candidate_count?: number | null; returned_count?: number | null; next_offset?: number | null; memory_id?: string | null; memory_ids?: string[]; delivery?: { host_visibility?: string; answer_use?: string } }>;
  } | null;
  time_window_activity?: {
    state?: "observed" | "not_observed";
    window_minutes?: number;
    start?: string;
    end?: string;
    event_count?: number;
    by_tool?: Record<string, { calls?: number; returned?: number; latest_at?: string | null }>;
    events?: Array<{ tool?: string; at?: string; returned_count?: number | null; research_id?: string | null; memory_id?: string | null; memory_ids?: string[] }>;
    items?: FlowEvidenceItem[];
    boundary?: string;
  } | null;
  time_window_guidance_activity?: {
    state?: "observed" | "not_observed";
    window_minutes?: number;
    start?: string;
    end?: string;
    event_count?: number;
    returned_count?: number;
    deferred_count?: number;
    ids?: string[];
    boundary?: string;
  } | null;
  instruction_receipt?: {
    instruction_version: string;
    content_sha256: string;
    core_text: string;
    source_file: string;
    stage: string;
    model_context_visibility: string;
  } | null;
  navigation_map?: {
    schema?: string;
    context_chars?: number;
    context_text?: string;
    preferences?: { status?: string; approved_count?: number; preview_count?: number; dimensions?: Array<{ id?: string; label?: string; count?: number; scopes?: Array<{ scope?: string }> }> };
    bank?: { status?: string; entity_count?: number; searchable_entity_count?: number; manifest_count?: number;
      hierarchy_coverage?: { total_memory_count?: number; indexed_memory_count?: number; unassigned_memory_count?: number; leaf_count?: number; generated_at?: string };
      topics?: Array<{ topic_id?: string; title?: string; navigation_summary?: string; source_count?: number; source_count_semantics?: string; memory_count?: number; children?: string[] }> };
  } | null;
  routes?: Record<string, string>;
  guidance_receipt?: {
    host_state?: string;
    coverage?: string;
    deferred_count?: number;
    deferred?: Array<{ id: string; revision?: string; reason?: string }>;
    guidance_items?: FlowEvidenceItem[];
    model_sections?: FlowEvidenceItem[];
    stable_profile_count?: number;
    preference_candidate_count?: number;
    stable_profile?: FlowEvidenceItem[];
  } | null;
  historical_audit?: {
    route?: string;
    state?: "observed" | "executed_empty" | "executed_no_result" | "not_observed" | "unknown";
    mode?: "hook_auto_recall" | "candidate_discovery" | "research";
    controller_state?: "admission_applied" | "not_in_candidate_path" | "not_used";
    candidate_count?: number | null;
    qualified_count?: number | null;
    rejected_count?: number | null;
    prepared_item_count?: number | null;
    returned_to_host_count?: number | null;
    unread_candidate_count?: number | null;
    delivery_state?: string;
    items?: FlowEvidenceItem[];
    admission_items?: FlowEvidenceItem[];
    deferred_items?: FlowEvidenceItem[];
  } | null;
};

export function projectFlowAudit(prompt: FlowPrompt) {
  const receipt = prompt.guidance_receipt;
  const history = prompt.historical_audit;
  const guidanceItems = [
    ...(receipt?.stable_profile ?? []).map((item) => ({ ...item, type: item.type ?? "stable_profile" })),
    ...(receipt?.guidance_items ?? []),
    ...(receipt?.model_sections ?? []).map((section) => ({ ...section, type: section.type ?? "fusion_model" })),
  ];
  const navigation = prompt.navigation_map;

  return {
    entry: {
      value: receipt?.host_state ?? prompt.routes?.entry_guidance ?? "not_observed",
      source: prompt.source ?? "unknown",
      coverage: receipt?.coverage ?? "unknown",
      instruction: prompt.instruction_receipt ?? null,
      taskState: prompt.task_state ?? null,
    },
    guidance: {
      count: guidanceItems.length,
      deferred: receipt?.deferred_count ?? 0,
      items: guidanceItems,
      stableProfileCount: receipt?.stable_profile_count ?? receipt?.stable_profile?.length ?? 0,
      candidateCount: receipt?.preference_candidate_count ?? receipt?.guidance_items?.length ?? 0,
      coverage: receipt?.coverage ?? "not_observed",
    },
    map: {
      receipt: navigation ?? null,
      l0: {
        status: navigation ? "observed" : "not_observed",
        contextChars: navigation?.context_chars ?? null,
        preferenceCount: navigation?.preferences?.approved_count ?? null,
        preferencePreviewCount: navigation?.preferences?.preview_count ?? null,
        dimensions: navigation?.preferences?.dimensions ?? [],
        topicCount: navigation?.bank?.manifest_count ?? null,
        topics: navigation?.bank?.topics ?? [],
        coverage: navigation?.bank?.hierarchy_coverage ?? null,
      },
      l1: {
        previewEntities: navigation?.bank?.entity_count ?? null,
        searchableEntities: navigation?.bank?.searchable_entity_count ?? null,
        topics: navigation?.bank?.topics ?? [],
      },
      l2: {
        actualRoute: history?.route ?? prompt.routes?.historical_memory ?? "not_observed",
        candidates: history?.candidate_count ?? null,
        returned: history?.returned_to_host_count ?? null,
        unread: history?.unread_candidate_count ?? null,
        items: history?.items ?? [],
      },
    },
    history: {
      value: history?.route ?? prompt.routes?.historical_memory ?? "not_observed",
      state: history?.state ?? prompt.routes?.historical_memory ?? "unknown",
      decision: prompt.history_decision ?? ((history?.state ?? prompt.routes?.historical_memory ?? "unknown") === "unknown" ? "unknown" : "needed"),
      decisionEvidence: prompt.history_decision_evidence ?? "not_observed",
      routeReceipt: prompt.memory_route_receipt ?? null,
      mode: history?.mode ?? (history?.route === "recall" || history?.route === "recall_and_research" ? "hook_auto_recall" : "not_observed"),
      controller: history?.controller_state ?? (history?.route === "recall" || history?.route === "recall_and_research" ? "admission_applied" : "not_used"),
      metrics: {
        candidates: history?.candidate_count ?? null,
        returned: history?.returned_to_host_count ?? null,
        unread: history?.unread_candidate_count ?? null,
        rejected: history?.rejected_count ?? null,
      },
      items: history?.items ?? [],
      delivered: history?.delivery_state === "observed" ? history?.returned_to_host_count ?? null : null,
      delivery: history?.delivery_state ?? "not_observed",
      evidenceDecision: prompt.evidence_decision ?? null,
    },
    timeWindowActivity: prompt.time_window_activity ?? null,
    timeWindowGuidanceActivity: prompt.time_window_guidance_activity ?? null,
  };
}
