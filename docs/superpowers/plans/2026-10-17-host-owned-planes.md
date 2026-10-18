# Host-Owned Planes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. User has selected continuous execution and delegated spec/plan self-review; preserve that method, no per-step permission prompts. One independent whole-change review at the end.

**Goal:** Derive record plane/authority from authenticated source roles, not model container choice.
**Architecture:** Versioned v3 flat item decoder reconstructs existing canonical planes. v2 and undeclared literal paths stay separate. Same immutable source, cache, budget, semantic review and storage pipeline.
**Tech Stack:** Existing Python/JSON/pytest and configured EP provider.
**Spec:** docs/superpowers/specs/2026-10-17-host-owned-planes-design.md

## Global Constraints

- No Provider/model/Key/default changes, production restoration/reset, GitHub/cloud writes.
- Same isolated ledger, counters preserved; total requests <=602, total tokens <=3868256, actual calls serial.
- Non-Git source: before snapshots and hashes instead of commits/worktree fabrication.
- Raw provider responses never rewritten; role correctness never substitutes for semantic or outcome qualification.

## Review Focus

1. Assistant quotations/reported user requests cannot become user requirements.
2. Mixed-role or forged card selection cannot silently gain host-derived authority.
3. v3 feedback must check flat items, but v2/undeclared callers must retain their own wire contract and cache boundaries.
4. Empty transport records and hidden source aliases cannot reappear in read_ids or inflate coverage.
5. Conditions, temporal updates and ambiguous scope must remain independently reviewed, not inferred from host role.

### Task 1: Versioned host-plane adapter

Files: new lib/scenario_hierarchical_host_planes.py, selection.py, coverage contract; new test_scenario_host_planes.py.
Interfaces: host_plane_registry(); host_planes_enabled(binding); decode_host_plane_proposal(request,proposal,resolve_cards)->canonical three-plane dict. resolve_cards(request,ids)->ordered original spans shared with v2.
- [ ] RED tests for actual role-derived placement, assistant quoting user, residuals, shared cards, unknown/mixed/forged cards, forbidden authority/container fields, v2 compatibility.
- [ ] Implement new registry and decoder, retaining exact source references and semantic values.
- [ ] Targeted tests and whole backend suite; preserve raw model response.

### Task 2: Request/feedback/receipt pipeline

Files: review.py, extraction.py, capacity.py; central controlled provider and affected fixture consumers.
Interfaces: review_binding defaults v3 only for explicit hierarchical flow; selection_schema(binding) validates v2/v3; selection_enabled remains bool; identity version unchanged semantic meaning but wire-bound cache stays separate. extraction_instruction(binding) chooses actual schema. mapping_feedback consumes both old three-plane proposals and v3 flat proposals using same decoder.
- [ ] RED end-to-end/feedback/cache tests before code; explicit semantic veto stays terminal.
- [ ] Implement actual host request, validation, decoder and per-item feedback; dynamic response schema, no hardcoded v2 under a v3 binding.
- [ ] Migrate only controlled test wire encodings for explicit v3, keep negative and old-version tests. Full backend suite.

### Task 3: Minimal real cycle then bounded qualification and integration

Files: isolated audit scripts and documentation; only owned product/test/config files mirrored.
- [ ] Back up exact initial source/runtime/target files; freeze hashes/source plans before API calls.
- [ ] One actual mixed-role task, inspect original stage receipts. If structural mismatch, diagnose before further calls; semantic failures remain failures, no repeat-to-green.
- [ ] Conditional natural regressions + controlled negatives under same ledger; compare unchanged independent references with actual reviewed records, report omissions and untested sources.
- [ ] One fresh independent review, one author Important/Critical TDD pass, full source/distribution regression and package scan.
- [ ] Owned-file parity, full production Python audit, fresh runtime import, six services and unchanged settings digest. No frontend claim or activation without evidence.
- [ ] Final report distinguishes engineering completion, model qualifications and unmeasured delivery/benefit.

Pre-flight/self-review: Task 1's decoder consumes the same source-card resolver as v2, no second source-ID authority. Task 2 must check version before reading proposal arrays and reconstruct feedback through the corresponding decoder. Task 3 cannot use before hashes as final protocol qualification; freezing comes after the final fix pass. All interfaces and stop conditions are explicit; no sample-specific rule or unspecified dependency identified.
