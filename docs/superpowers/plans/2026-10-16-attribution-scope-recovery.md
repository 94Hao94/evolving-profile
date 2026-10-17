# Attribution, Scope and Context Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Execute inline with one final independent review, as already selected by the user. TDD for each repair.

**Goal:** Preserve faithfully attributed conversation items while isolating unresolved scope, recovering bounded original context before rejection and never promoting assistant reports into verified outcomes.

**Architecture:** Repair the existing hierarchical_review.v1 internal flow, four existing read views and status card. Add an explicit versioned judgment response alongside conservative legacy compatibility; current source/protocol fingerprints invalidate incompatible receipts. This implements the already approved spec's local-valid/local-unknown and separate-axis contract, not a new memory plane or new product version.

**Tech Stack:** Python, SQLite, existing configured Provider, Next.js/React/next-intl.

**Spec:** ../specs/2026-10-16-hierarchical-evidence-review-design.md §§1.1,5,7.4,8,9,11,13, plus the user's approved in-chat four-part repair design.

## Global Constraints

- Do not modify the default segment_coverage.v1/source_shadow/model_trial=false configuration, Provider, credentials, models, JEV/RAG/risk settings, backups or GitHub.
- Keep exact sources, Unicode quotations, roles, permissions, source revisions, legacy failures and parent attempts. No blanket loosening and no reinterpretation of a legacy accept=false as true.
- Independent grant diagnostic-02 remains at its original cap8 requests/128000 Token; already4/10111, unknown0. Never reset or combine it with the old grant. Real requests only if a complete declared diagnostic fits; no full-history re-extraction.
- Source, intent attribution, scope and external outcome are independent. Partial navigation is not verified facts, global completion, external success or mandatory guidance.
- Use shared registry values and ZH/EN labels with explicit existing-locale fallbacks. Source language never translated by UI.
- Preserve private/runtime/public distribution boundaries; non-Git source uses owned-file backups and durable audit, no fabricated worktree or commit.

## Review Focus

1. A typed axis response contradicts an old explicit rejection: reject conflicting contracts; never wash the old veto.
2. Context reads seek nearby messages but accidentally cross Session/source/permission boundaries: same immutable snapshot only; no model-provided paths.
3. An unresolved identity hides an otherwise faithful requirement, or becomes a guessed project: retain literal candidate/attribution, block scope promotion.
4. One failed leaf aborts later independent leaves or a parent claims missing child complete: preserve fixed denominator and reviewed subgroups; skip incomplete parents.
5. New context invalidates old cache or consumes unbounded money: source-bound context manifest, at most2 rounds/3 units, all calls in original grant, stale-context rebind prohibited.

## Task 1: Typed judgment boundary

**Files:** config/scenario-coverage-contract.json; host-adapter/lib/scenario_hierarchical_judgments.py (new); scenario_hierarchical_review.py; scenario_hierarchical_execution.py; scenario_intent_atoms.py; test_scenario_review_axes.py (new).

**Interfaces:** normalize_judgments(result, stage) returns normalized attribution/scope/outcome axes or a contract error. execute_review emits only host-sealed reviewed/needs_context/rejected receipts. Legacy true follows existing strict checks; legacy false remains rejected. Typed responses never use accept and never assert verified external outcomes.

- [ ] RED: faithful attribution plus unresolved scope remains inspectable; defective attribution rejects; needs_context is not accepted; conflicting/unknown/malformed axes reject; restore binds original charged receipt.
- [ ] GREEN: add registry schema and explicit typed protocol contract; keep legacy checks and source read IDs.
- [ ] Verify: api/.venv/bin/python -m pytest -q host-adapter/test_scenario_review_axes.py host-adapter/test_scenario_hierarchical_review.py host-adapter/test_scenario_intent_atoms.py (all pass).

## Task 2: Source-bound pre-leaf context

**Files:** scenario_hierarchical_context.py (new); scenario_hierarchical_review.py; scenario_hierarchical_incremental.py; test_scenario_review_context.py (new).

**Interfaces:** bounded context recovery receives snapshot/partition, valid review, same-snapshot raw root, executor and current permission; returns last review, exact original pages and explicit stop reason. Registry owns max_rounds=2/max_units=3. Context pages are data, role/order/provenance retained, partial page never complete. Receipts with external context do not rebind across source generations without that context revalidation.

- [ ] RED: actual neighboring original supplies missing referent before a second leaf review; no neighbors causes zero repeated calls and explicit unresolved; stale permission/source blocks; arbitrary path/unknown span never selects context; repeats and capacity are bounded.
- [ ] GREEN: select only nearest authorized nonempty original units, check full wire capacity, retain original page bounds and ordered hashes, dispatch only charged explicit recovery.
- [ ] Verify: test_scenario_review_context.py plus raw readback/cache regressions all pass.

## Task 3: Partial retention and scope isolation

**Files:** scenario_hierarchical_pipeline.py; scenario_relation_obligations.py; scenario_hierarchical_transport.py; scenario_hierarchical_read.py; test_scenario_review_partial.py (new).

**Interfaces:** graph stores reviewed atoms separately from source-bound unreviewed candidates, leaf scope blockers and context attempts. All target leaves remain fixed. assess_hierarchical_scope derives unresolved leaf scope from valid receipts, not caller suppression; no parent closes an incomplete child.

- [ ] RED: ambiguous leaf retains original-supported content and unresolved scope; second independent leaf still reviewed after first semantic rejection; unreviewed candidates never report reviewed; contextual counts differ from host source delivery; stale removes all old green axes.
- [ ] GREEN: integrate recovery, retain candidates/deficits and continue independent work; only current verified leaves enter capsules; scope uncertainty blocks group/ancestors, not literal storage. Add attribution/scope/outcome axes to existing read projection.
- [ ] Verify: all new partial tests, original relation/end-to-end/read/binding tests pass.

## Task 4: UI, deployment and honest acceptance

**Files:** console/src/components/scenario-coverage-details.tsx; console/src/messages/*.json; console/tests/components/scenario-hierarchical.test.ts; operations doc; audit acceptance/owned manifest.

- [ ] RED: ZH/EN status shows attribution, scope, outcome and background context separately; unknown never zero/verified, legacy still readable.
- [ ] GREEN: additive compact labels only, no new configuration toggles or menus; existing scroll/opaque details retained.
- [ ] Run whole private and public backend suites, Web suite, TypeScript/build/package; one final fresh-context code review, fix important findings with RED→GREEN and repeat affected full gates.
- [ ] Mirror only owned changes; reload Console only if changed UI needs it; APIs/Retain/Worker untouched. Real browser click/scroll/ZH/EN checks on installed build.
- [ ] Freeze current implementation and same-source diagnostic plan using unchanged remaining grant; execute only if complete declared minimum fits4 remaining, retain all7 original source cases and tuning annotations. Never manufacture answer-use evidence or qualification.
- [ ] Report engineering, semantic state, old/new budgets, actual installed/native-loaded version and unresolved gates separately; no release/publish claim without evidence.

## Self-review and execution ruling

The user approved these four repairs in chat and earlier explicitly delegated author review followed by continuous execution. This plan restores behavior already required by the approved written spec; no new subsystem, model switch, budget or global permission. Continue inline under that authorization rather than introducing another between-task approval stop. Cost: final independent review must scrutinize the typed/legacy boundary and partial-navigation semantics. Preserve this audit workspace because private source is not Git.
