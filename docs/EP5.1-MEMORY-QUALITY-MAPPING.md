# EP5.1 Canonical Receipt Mapping

This mapping is the first implementation contract for the Memory Quality Engine.
It projects existing prompt-bound receipts into `memory_quality_event` without
creating a second retrieval path or changing memory truth.

## Source precedence

1. Prompt-bound `memory_route_receipt.tool_events` and `guidance_receipt` are the
   primary route observations.
2. `historical_audit` supplies bounded candidate/delivery evidence when the
   route event does not carry it.
3. `time_window_activity` is only used when its boundary is
   `same_prompt_binding_only`; unattributed activity remains `not_measured`.
4. Missing evidence is `not_measured`, never numeric zero.

## Canonical cases

| Case | Plane / route | Status | Candidate | Returned | Delivered | Meaning |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `no_call` | selected route | `not_called` | null | null | null | A route was required or shown, but no bound tool call was observed. |
| `called_empty` | user/agent history | `returned_zero` | known or null | 0 | 0 | The bound tool call completed and returned an empty result. |
| `preference_only` | user memory / `user_preference` | `delivered` or `returned` | known | known | known | Preference guidance was delivered; this does not imply historical Recall. |
| `history_only` | user/agent memory | `returned`/`delivered` | known | known | known/null | Historical route was called independently of preferences. |
| `mixed` | user memory + agent process + RAG | per-event | per-event | per-event | per-event | Parallel routes stay separate; parent totals are not copied to children. |
| `agent_process` | agent process | route-specific | known/null | known/null | known/null | Process memory is shown only from a prompt-bound process receipt. |
| `external_rag` | external RAG | route-specific | known/null | known/null | known/null | External documents remain outside EP user/agent memory. |

## Hard projection invariants

- `null` means not measured or unavailable; `0` means an observed empty result.
- Every event retains prompt/session/project identity when available.
- `candidate_count`, `returned_count`, and `delivered_count` are not inferred
  from one another.
- `answer_use` and model attention are not inferred from host visibility.
- Parent lane counters are computed from child events only; no child receives a
  copied aggregate.
- The projection is deterministic and read-only; Lightweight mode performs no
  LLM call and no additional Recall/Research.

## Implementation decision

The first implementation is a pure TypeScript projection over existing
`FlowPrompt`/`FlowReceipt` data. A later append-only ledger can persist the
result, but the console can already render correct status and counts without a
parallel capture pipeline.
