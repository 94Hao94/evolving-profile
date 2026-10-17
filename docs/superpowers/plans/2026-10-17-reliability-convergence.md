# EP5.1 Reliability convergence — completion addendum

Binding spec: `docs/superpowers/specs/2026-10-16-hierarchical-evidence-review-design.md`, especially §5, §9, §10 and §13. Existing inline execution/self-review authorization remains; this addendum clarifies unfinished fixes, not newly approved release or model configuration.

## Constraints

No production attempt resets, source edits, historical failure deletion, provider/model/Key changes, full-history processing, protocol-default enablement, cloud or GitHub publishing. Reuse the existing diagnostic grant with all used counts retained. Public distribution has unrelated dirty edits; mirror only owned paths. No claim of answer benefit without actual answer evidence.

## Task 1 — daily multi-turn preservation

Modify scenario_model.py and scenario_review_catalog.py. Add source-turn navigation inventory listing each user ID and subsequent assistant candidates without asserting answeredness. Add explicit host episode first/last/membership to review input; current goal anchors never redefine membership. Keep existing v3 state schema and exact correction selection. Tests exercise serialized provider inputs and review transport, including append, multiple assistant candidates, role boundaries and empty sources. Run focused tests RED/GREEN, then the existing real 8-message source in isolation; do not publish a failed reviewer verdict.

## Task 2 — proposal is not review

Modify hierarchical review/execution/extraction interfaces: extraction requires only authenticated proposal shape and optional context requests, status `proposed`; independent leaf keeps review axes and accepted scope mandatory. Cache restoration must retain stage-specific authority and reject proposal-as-review. New stage contract participates in protocol fingerprint. Test producer without self-verdict, invalid proposal, replay, leaf-forgery and all old leaf gates.

## Task 3 — bounded local output recovery

Only an actual provider `coverage_response_incomplete` extraction failure may split that failed raw window. Preserve source order, exact disjoint primary span union, source/permission bindings, original failed receipt and all charged usage. Never split away a semantic rejection or HTTP failure. Effective children enter normal extraction and independent leaf stages and replace the parent only in the effective plan, not historical receipts. Bound depth 3, minimum primary 128 UTF-8 bytes, at most 16 additional windows per root; shared budget is the final limit. Leaf/merge output truncation stays partial initially. Test Unicode, no gaps/overlaps, persistence/resume, minimum/depth/budget stops, unaffected sibling reuse and semantic-veto non-retry.

## Task 4 — evidence and handoff

Freeze code before real replay, use minimal cases before all seven; preserve old positives and failures, mark tuned data honestly and add untouched holdouts only before tuning. Run host/guidance/status/controller and script regression, Console tests/tsc/build if any UI-affecting paths change. One final fresh-context code review; fix Important/Critical with RED→GREEN. Sync only owned validated files, record runtime provenance separately from source. UI schema unchanged unless evidence requires a corresponding small change. Defaults stay old source_shadow/model_trial=false. Report engineering, actual semantic results, costs and unanswered benefit separately.

Review focus: proposal authority cannot leak into leaf; dynamic partitions cannot invent coverage; metadata cannot erase human text; appended source invalidates old generation; semantic veto and unknown usage remain visible.
