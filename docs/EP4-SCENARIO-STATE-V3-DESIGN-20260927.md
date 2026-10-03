# EP4 Scenario State V3 Design

## Objective

Replace quote-length variants with three useful Session Scenario Summary tiers while preserving source provenance and avoiding completion claims that the conversation cannot support. This is a navigation layer, not Bank fact verification. Existing V2 published rows remain valid and untouched.

## State Contract

A V3 draft contains a `state` object with `subject`, `goal`, `phase`, `constraints`, `corrections`, `assistant_reports`, and `unresolved`. Every non-empty claim has concise text and one or more original message IDs. The phase is one of `requested`, `in_progress`, `assistant_reported`, or `unknown`; no automatically generated phase means externally verified completion. A final user request with no subsequent assistant response forces `requested` and an unresolved item. Claims from assistant messages remain explicitly assistant-reported.

Structured form replies are parsed as JSON, preserving the raw message ID and source hash. The model receives a human-readable question/answer representation with `structured_user_answer` provenance. Malformed wrappers remain visible as opaque source but cannot become a claim without source review. Raw rollout data is never rewritten.

## Tiers And Evidence

The renderer builds compact from subject, goal, current phase, and the most important unresolved item. Standard adds decisive constraints and later corrections. Full adds a bounded chronological explanation and source message locators. Every tier is independently useful, respects existing Session character/token budgets, and declares its navigation-only role. The full tier is not the complete conversation or a direct source read.

The model proposes state claims. Code verifies schema, allowed source IDs, role-to-field mapping, source revision, phase compatibility with the final message, and tier budgets. It cannot prove semantic entailment, so model review checks source alignment and stage precedence; human review remains required before publication. A model pass cannot bypass the manual gate. Rejected drafts and prior index content remain recoverable.

## Evaluation And Release

Start with the two previously rejected high-frequency Sessions plus held-out examples: competing projects, unresolved final request, structured form answer, stale assistant completion report, and a closed conversation. Compare V3 with V2 for independent compact identification, latest correction, provenance, unsupported completion, and unread source coverage. Publish only individual drafts that pass model and manual review; do not batch-promote the 151 pending rows or workspace buckets to verified Projects.

Desktop MCP visibility and WPS cloud-backup scheduling are separate operational checks. A healthy service or CLI call is not proof that the current Desktop chat exposed the tool. No cloud upload is authorized by this summary-quality change.
