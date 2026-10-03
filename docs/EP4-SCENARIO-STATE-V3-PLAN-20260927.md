# EP4 Scenario State V3 Implementation Plan

**Goal:** Produce source-linked, state-based three-tier Session summaries and publish only independently checked examples.

**Architecture:** Add a V3 state module beside the V2 extractor. Keep raw source immutable, model output untrusted, and the existing index/promotion gate as the only publication path. Add V3 selection to the pilot CLI, then evaluate with existing private Sessions.

**Spec:** `docs/EP4-SCENARIO-STATE-V3-DESIGN-20260927.md`

## Tasks

1. Add structured form parsing and typed source messages. Test valid and malformed wrappers, source IDs, and role preservation before implementation.
2. Add V3 state validation and deterministic tier rendering. Test object identity, source-linked claims, latest-user unresolved phase, assistant-report boundaries, and budget failures before implementation.
3. Add V3 model draft and review requests to the existing pilot; extend fingerprint and promotion validation without changing V2 hashes. Test transport payloads and rejection paths before implementation.
4. Run source/model/manual evaluation on the two prior failures and held-out cases. Publish only passing rows through the existing atomic publisher. Verify runtime synchronization, host exposure separately from CLI, backup diagnostics, and regressions.

## Global Constraints

- No Bank fact, experience, entity, or preference rewrite.
- No model pass or summary title upgrades a Project identity or proves external delivery.
- Preserve V2 compatibility and source-revision checks.
- No bulk promotion or GitHub publication.
- Failed review remains failed; do not erase or reinterpret rejection to increase pass rate.
