export type FlowLane =
  | "ingress"
  | "guidance"
  | "user_memory"
  | "agent_process"
  | "external_rag"
  | "model_context"
  | "execution_writeback";

export type FlowStatus =
  | "disabled"
  | "not_applicable"
  | "not_requested"
  | "available"
  | "observed"
  | "candidate_returned"
  | "gated"
  | "delivered"
  | "verified"
  | "empty"
  | "unavailable"
  | "failed"
  | "not_observed"
  | "unknown";

export type FlowReceipt = {
  trace_id: string;
  parent_trace_id?: string | null;
  prompt_id?: string | null;
  turn_id?: string | null;
  session_id?: string | null;
  project_id?: string | null;
  lane: FlowLane;
  stage: string;
  status: FlowStatus;
  started_at?: string | null;
  finished_at?: string | null;
  candidate_count?: number | null;
  returned_count?: number | null;
  delivered_count?: number | null;
  token_count?: number | null;
  source_type?: string | null;
  source_ids?: string[];
  evidence_ids?: string[];
  summary?: string | null;
  error?: string | null;
};

export type FlowLaneSummary = {
  lane: FlowLane;
  status: FlowStatus;
  receipts: FlowReceipt[];
  counts: { candidates: number; returned: number; delivered: number; tokens: number };
};

export const FLOW_LANES: FlowLane[] = [
  "ingress",
  "guidance",
  "user_memory",
  "agent_process",
  "external_rag",
  "model_context",
  "execution_writeback",
];

export function summarizeFlowLane(lane: FlowLane, receipts: FlowReceipt[]): FlowLaneSummary {
  const counts = receipts.reduce(
    (acc, receipt) => ({
      candidates: acc.candidates + (receipt.candidate_count ?? 0),
      returned: acc.returned + (receipt.returned_count ?? 0),
      delivered: acc.delivered + (receipt.delivered_count ?? 0),
      tokens: acc.tokens + (receipt.token_count ?? 0),
    }),
    { candidates: 0, returned: 0, delivered: 0, tokens: 0 },
  );
  const status: FlowStatus = receipts.length ? (receipts.some((r) => r.status === "failed") ? "failed" : receipts.some((r) => r.status === "delivered" || r.status === "verified") ? "delivered" : receipts.some((r) => r.status === "observed") ? "observed" : receipts[0].status) : "not_observed";
  return { lane, status, receipts, counts };
}
