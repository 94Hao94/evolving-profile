# Evolving Profile 5.2.0

> Contribution release notes. The product version is authoritative in `VERSION` and `config/release-manifest.json`.

## Why 5.2.0

EP 5.2.0 turns the person/contact requirement into a first-class, source-bound record plane and carries the latest retrieval, host-compatibility, and operational evidence work into a sanitized public release. It is additive to User Memory and Agent Process Memory: raw transcripts and original evidence remain authoritative, while structured records make explicit lookups practical.

## Main changes

### 1. Source-bound personal records

- Adds a local `ep.personal-record-index.v1` for user-supplied person, contact, identity, vehicle, organization, role, address, and credential-reference fields.
- Captures mobile phones, landlines, email addresses, national IDs, vehicle plates, names, organizations, roles, addresses, and credential references without placing private values in the public repository.
- Keeps the index local with mode `0600`; every row carries source text hash, host, session, turn, transcript path, observation time, verification state, relation confidence, and related fields.
- Exposes the read-only `personal_record_search` MCP surface for explicit lookup by name, phone, landline, email, ID, plate, or credential reference.

### 2. Evidence-first relationship binding

- Explicit labels (`联系人`, `负责人`, `项目负责人`, `部门联系人`, and their English equivalents) can bind a field to a person.
- Structured person blocks such as `name → phone → national ID` are parsed as independent groups.
- A single named person can receive message-level fields; multiple people never share fields by list order.
- Ambiguous co-occurrence remains `unbound`; no same-name merge is performed without subject, relation, time, scope, and source evidence.
- Corrections are append-only and preserve the original source; a corrected name is represented as a correction/supersession relation rather than a destructive rewrite.
- False-positive labels and generic student-profile names are retained as source history but excluded from active person search.

### 3. Retrieval and evidence contracts

- Historical-cause and comparison prompts can take a multi-route plan that combines User Recall, Agent Recall, live audit, and source readback when required.
- Route receipts separate `not_required`, `not_retrieved`, `retrieved_no_candidate`, `candidate_unverified`, and `source_read` states.
- Research navigation, source readback, coverage contracts, candidate counts, and answer-use uncertainty remain distinct; navigation-only candidates are never promoted to facts.
- Prompt ingress writes personal-record candidates early, so lookups do not depend on a later Stop hook.

### 4. Host and session compatibility

- Shared host profiles cover Codex, Trae, WorkBuddy, Claude Code, Claude Desktop, Hermes, Doubao Work, and generic MCP clients.
- Host, process, session, turn, transcript, and receipt identifiers remain separate fields.
- The published matrix distinguishes `documented`, `host_verified`, `partial`, `unverified`, and `not_measured` for MCP stdio, HTTP/SSE, prompt hooks, stop hooks, tool hooks, and automatic capture.
- Codex, Trae, and WorkBuddy statuses preserve their actual measured boundaries; Claude Desktop remains explicitly deferred for live-client acceptance.

### 5. Operational quality and release controls

- Runtime/source/release parity remains hash-audited.
- Audit rotation, backup restore drills, release gates, SLO snapshots, host transport matrices, process-temp cleanup, and mcp-activity semantics are retained in the operational evidence layer.
- The public package remains sanitized and re-initializable: no personal Bank, host transcripts, runtime receipts, API keys, or local credential values are published.

## Compatibility

- Existing facts, experiences, entities, observations, preferences, scenario summaries, Agent Process Memory records, L0/L1/L2 navigation, and legacy route aliases remain additive and backward compatible.
- The personal-record index is local and optional; disabling retrieval does not delete captured records.
- Existing hosts must reconnect or restart their MCP child when a long-lived process has already loaded an older adapter module.
- Real client acceptance is host-specific. A configured transport or visible MCP tool is not itself a passed native-client test.

## Known boundaries

- A source locator or navigation candidate is not an independently verified fact.
- A tool receipt proves call and delivery state, not opaque answer adoption.
- Historical personal fields without an explicit same-source person binding remain unlinked.
- Claude Desktop live-client acceptance, full Trae/WorkBuddy transport coverage, remote WPS readback, and secret migration are outside this release claim.
