# Source Selection Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, one fresh whole-change review at end. User has delegated self-review and continuous execution; no per-task approval prompts.

**Goal:** Remove model-generated literal source references and ambiguous relation structures without weakening semantic acceptance.
**Architecture:** A source-selection.v2 wire adapter translates fixed-card proposals into the existing authenticated evidence flow. Source identity and semantic identity are versioned separately. Typed relation outputs reconstruct a canonical view without modifying original responses.
**Tech Stack:** Existing Python host adapter, JSON contract, pytest; existing configured EP model only.
**Spec:** docs/superpowers/specs/2026-10-17-source-selection-contract-design.md

## Global Constraints

- Default source_shadow/model_trial=false/segment_coverage.v1 unchanged; no Provider/Key/GitHub/cloud/production restoration.
- Same request/Token ledger and old attempts; non-Git private tree uses exact backups/SHA, not fabricated commits.
- Model proposals and host canonical views remain distinct; unknown scope and semantic veto stay blocked.
- Actual wire capacity, source/permission/version and cache checks apply to every stage.

## Review Focus

1. Shared cards must not permit duplicate semantic items, role forgery or false character coverage.
2. Wrong-prefix/unknown/duplicate IDs and mixed old/new output forms cannot be repaired into authority silently.
3. Canonical reconstruction and cache restore must preserve original HTTP responses and version bindings.
4. A faithful report of failed/unverified work must not become a verified outcome or erase identity ambiguity.
5. Card catalogs, frontier and source pages must fit actual provider envelopes without hiding original text.

### Task 1: Card protocol adapter and identity

Files: new lib/scenario_hierarchical_selection.py; modify scenario_intent_atoms.py; new test_scenario_selection_contract.py.
Interfaces: selection_cards(inputs,aliases) -> list[dict]; decode_selection_proposal(request,proposal) -> canonical dict; identity_version_from_binding(binding) -> str. validate_atom_proposal(...,identity_version='source_offsets.v1') accepts explicit source_semantics.v2 only from host.
- [x] Write RED tests for exact card expansion, multilingual text, same-card distinct intents, duplicates, forged/mixed refs and role mismatch.
- [x] Implement pure adapter and explicit ID version. Keep old default IDs and duplicate checks.
- [x] Run targeted tests; record RED/GREEN and mutation-sensitive assertions.

### Task 2: Bind wire format into real extraction/review pipeline

Files: scenario_hierarchical_review.py, scenario_hierarchical_extraction.py, scenario_hierarchical_capacity.py, scenario_hierarchical_incremental.py, scenario_hierarchical_pipeline.py, config/scenario-coverage-contract.json; central controlled test provider and affected tests.
Interfaces: host review_binding includes wire_contract; build_review_request emits typed aliases/cards only when declared. expand_selected_aliases expands raw selected-card proposals; extraction feedback retains a bounded failed proposal when card mapping is invalid. bind_leaf_review uses explicit host identity version.
- [x] Write RED end-to-end tests for multi-intent shared card and no legacy-literal bypass under v2; old undeclared direct requests remain compatible.
- [x] Implement actual request/receipt/cache path; canonical source_refs remain host-derived and raw result unchanged.
- [x] Run full backend suite; resolve failures by actual contract, not fixture-only production branches.

### Task 3: Typed relations and outcome boundary

Files: selection adapter, review.py, relation_obligations.py, pipeline.py; new test_scenario_selection_relations.py.
Interfaces: decode_selection_relations(request,result) -> old canonical obligations/object_links/group_states. No model-provided outcome exemption. Host-derived unverified assistant report notes stored separately from record obligations.
- [x] Write RED tests: distinct endpoints, source/intent confusion, missing pair, wrong/mixed fields, actual original pages, raw-response immutability and cached malformed results.
- [x] Implement strict enum/shape/ID validation before reviewed seal; preserve direction and semantic kind in canonical rows.
- [x] Test faithful failed report and unresolved identity separately; no reason-keyword stripping.

### Task 4: Verification and controlled integration

Files: current audit scripts only; owned product files sync after verification.
- [ ] Freeze source hashes and same original source scopes; preflight all seven without paid calls.
- [ ] Extend only original isolated request allowance if needed under prior explicit test-expansion authority, keeping counters and Token cap.
- [ ] Actual configured-provider minimal cycle + negative controls, then fixed complete cases/new natural probes. Preserve all nonpassing results.
- [ ] One fresh independent read-only final review; Important/Critical fixes each RED→GREEN plus full suite, no re-review loop.
- [ ] Full source/distribution regression, package scan, narrow sync with baseline checks, fresh runtime import and six live routes/default digest.
- [ ] Final PRD/plan audit distinguishes engineering completion, model results, all-seven-source qualification and answer benefit; never claim unmeasured activation success.

Pre-flight: Task 2 consumes Task 1 adapter and identity_version; Task 3 consumes the same typed catalog and raw-to-canonical reconstruction. Neither may create a second alias/source registry. Task 4 freezes versions after implementation before paid testing. No conflicting acceptance semantics found; unresolved runtime model quality is an explicit evaluation result, not a promise.
