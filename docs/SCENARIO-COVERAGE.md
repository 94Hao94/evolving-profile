# Bounded long-session coverage

The new coverage path defaults to **source_shadow**: source structure and navigation inventory only, zero additional EP model requests, no replacement of accepted legacy v3 summaries. It does not reprocess all history automatically. Original transcripts, previous rejections and original job attempts remain intact.

## Configuration and inspection

Open Bank configuration → Scenario summary. The coverage panel controls the mode, explicit model pilot and advanced resource limits. Saving this panel updates coverage settings only, not Provider credentials. The selected Session's existing Scenario summary detail shows source watermarks, global versus local review, requirements, correction links and bounded original-record readback. English and Simplified Chinese labels are complete; other supported locales explicitly fall back to English for this panel. Original user text is not translated.

The registry is `config/scenario-coverage-contract.json`; runtime overrides are `scenario_coverage` in the installation's runtime settings. The installed Python registry and the Console build must be deployed together.

## Exact-source preparation

Use the installation's existing worker; substitute the actual state root, native Session root, owning Bank and exact Session UUID:

```sh
python3 host-adapter/context-incremental-worker.py \
  --coverage-source \
  --state-root /path/to/ep-state \
  --session-root /path/to/native-sessions \
  --bank-id personal-memory \
  --session-id 00000000-0000-4000-8000-000000000001
```

Only indexed, authorized sources with matching ownership are processed. Protected, unknown-scope and explicitly no-memory-write sources remain blocked. Preparation does not claim or reset the old summary job. It does not call the Provider in source_shadow mode. One decoder stays alive across bounded leases; an interrupted compressed stream replays and verifies its prefix rather than seeking a decompressed offset in a compressed file.

An optional local `zstd` executable enables compressed JSONL. Missing decoder, corrupt input, unknown native schema and oversized records have explicit unavailable/invalid/partial outcomes; do not interpret them as source absence. The installer only checks availability and never installs a decoder during a read request.

## Trust and cost boundaries

- Source structure complete is not semantic acceptance or external fact verification.
- Local review acceptance does not establish whole-source acceptance. Required global partitions, correction boundaries and unresolved conflicts remain separate.
- Requirement and intent IDs bind the source snapshot, raw record hashes, roles, scope and spans. A source change or stale cursor cannot reuse old acceptance silently.
- New navigation uses `segment_coverage.v1`, not legacy v3 acceptance. Preview text can omit conditions; unread requirements and raw-source obligations remain explicit.
- Assistant reports stay unverified claims. A covered request is not independently verified task completion or delivery to an agent host.
- The initial explicit model pilot is tightly bounded (at most two requests / 16000 reserved input-plus-output tokens per selected parent). Existing spent attempts/charges remain. This is a small experimental pilot, not a guarantee that every long source will finish semantic review.
- Before the first genuinely new API request, the installed worker reserves one shared remaining parent attempt. A per-Session lease prevents a legacy worker or reassessment from spending that same slot concurrently. Cache-only reuse does not consume another parent attempt. The original summary status is not rewritten to new-contract success.
- Already-configured fallback Providers are tried only for transport failures, with a separate reservation for every request. A semantic rejection is never retried against other models to fish for acceptance. Explicitly rerunning a transport failure can use only the original residual allowance; unknown prior usage remains charged. A fallback may use the small pilot's remaining request slot and leave global review paused. No hidden free retry is performed inside the HTTP adapter.
- Equivalent raw units and unchanged structural partition drafts can be reused after append, with fresh snapshot IDs and source validation. They are not reused semantic acceptance. Same-generation accepted review receipts require an exact source/input/Provider binding. New generations may use only the original unspent request/token allowance; Bank, project or effective-policy changes cannot inherit another owner's allowance.
- A changed semantic generation or model may require more review than the remaining parent budget permits. The system pauses; it does not buy new attempts or tokens by changing normalization, codec, scope or Provider.
- Long raw records, oversized global requirements, decoder/replay limits, unavailable codecs and exhausted budgets remain visible partial/unknown outcomes. Do not truncate negation or required source text to manufacture acceptance.

MCP `read_scenario_summary` retains its old call form. Optional `coverage_view` values are overview, requirements, relations and source; the source view requires an exact `coverage_requirement_id`. Requirement/relations cursors bind current source and ledger/navigation revisions. Explicit raw readback checks original-record hash and role, including verified selected-record materialization for prepared compressed sources. Native Codex MCP processes may require a host reload after a tool-schema update; a fresh-process verification is not proof that an older cached host reloaded.

## Validation

`scripts/verify-scenario-coverage.py` replays 1–32 explicitly selected sources in a canonicalized temporary state directory. It performs no Provider calls, source edits or legacy promotion. Supply `--state-root`, `--session-root`, repeated `--session-id` and a new `--output` path. Its result distinguishes structural completion from semantic review and reports all partial outcomes. Controlled callbacks test protocols, not live model quality.
