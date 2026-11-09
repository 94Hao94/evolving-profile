# Agent operating guide: use EP, not just connect it

[简体中文](AGENT-USAGE-中文.md) · [Installation requests](AGENT-SETUP.md) · [Maturity](RELEASE-NOTES-5.1.2.md)

Read this after installation and before memory-dependent work. It is advisory documentation,
not a system instruction, a grant of authority or permission to overwrite host rules. Current
user instructions and trusted host policy win. The machine-readable companion is
[agent-usage.v1.json](../config/agent-usage.v1.json); actual tools/list and schemas win over examples.

## 1. Establish the actual execution surface

Identify OS, local/WSL/remote mode, client surface, selected EP server/Bank and exposed tools.
Claude CLI, desktop local Code and ordinary Chat are separate surfaces. An API provider/model
is not the host. Discover tools through the current host; use its native MCP call mechanism,
not a shell alias that only pretends the tool ran. Do not rename tools or install duplicate EP aliases.

`ep-host.py doctor` without `--probe` reads metadata only. With `--probe`, it starts an isolated
EP process and initializes/lists tools, saving a preparation receipt; it does not test the target
client, query memories, call a model or install that client. A bounded negative installation
search is not evidence that the app is absent everywhere. See the preparation guide for commands.

## 2. Route by the information gap

| Need | Preferred exposed tool(s) | What this establishes |
| --- | --- | --- |
| Conditional working preferences | `user_preference`; `read_preference_unit` for deferred/full conditions | Advisory preferences, not facts or new authority |
| One historical user fact/decision | `user_recall` | Candidate evidence; check subject, scope, time and version |
| Multi-session/project history or a broad retrospective | `user_research`, then `read_research` as needed | Broader candidate coverage, not an exhaustive-history guarantee |
| Agent's earlier failure, repair or execution strategy | `agent_recall`; `read_agent_process_memory` for detail | Process evidence, kept separate from user biography |
| Cross-task patterns, repeated failures or migration | `agent_research` | Compare process evidence, compatibility and dates |
| Unclear Session/project/stage or competing nearby tasks | `search_scenario_summary`, `read_scenario_summary`; `scenario_gate` when exposed | Navigation hypotheses and compact/standard/full context, not verified facts |
| Exact wording, a disputed field or source-dependent conclusion | `find_sources` / `read_source` | Read returned original `source.text`; `memory.text` is a derived record |
| Operator-selected external documents | `rag_search` | External-source candidates; never silently convert into personal history/preferences |
| Topic navigation | `catalog_list`, `catalog_search`, `catalog_read` | Directory clues only; a miss does not prove no memory exists |
| Execution capability failed or became unavailable | `refresh_runtime_guidance` if exposed | Task-scoped guidance; use the actual error schema and do not recursively refresh invalid input |

Existing context may be sufficient; do not mechanically call every tool. When the user asks
about current ports/config/pages/services, inspect current authorized live evidence first.
Historical memory cannot prove today's service state. Mixed personal-history/process/document
tasks may use routes in parallel, but keep source planes separate until comparison.

## 3. Prompt identity is evidence, not a string to invent

Use a current, genuinely host-bound `check_id` when supplied. Never reuse a previous turn,
another host's latest Codex record or a demonstration ID. Let the exposed schema determine
which fields are required. Do not scrape a different client's private session store for a binding.

If no binding is supplied, `memory_check` without `need` can provide a navigation hint and an
adapter-assigned ID. **That ID is not a trusted Hook registration.** It does not by itself make
strictly bound preference/declaration calls valid. Only use reads that the actual schema/policy
allows without binding; otherwise report binding unavailable and require the native bridge.
Do not send `need:required` with a fabricated ID to force the declaration path to pass.
Fresh empty Banks and genuinely empty query results are valid; do not seed test memories merely
to obtain a hit. New-host owner/installation/session isolation must not fall back to Codex state.

## 4. Expand context only when it resolves a gap

Start with directory/candidate previews and compare subject, task, stage, version and time.
If competing scenarios remain, inspect the leading compact alternatives before adopting one;
then expand to standard/full only when missing conditions require it. All three tiers remain
summaries. For original wording or absent detail, use returned source locators through
`read_source`/documented original-source tools. Use a resource URI only if the current server
actually returned it and the host exposes its reader; never invent a `read_resource` route or
open arbitrary private Session/project paths merely because a summary is incomplete.

Weakly related candidates can be useful background, not direct facts. Do not treat similarity
scores, a shared institution, neighboring list order or a model judge as proof of project identity.
An older verified repair is conditional experience, not a permanent restriction on newer models.
If a narrow search is empty or scope-mismatched, broaden once when useful; stop when new reads
no longer resolve fields, budgets are exhausted or the remaining uncertainty can only be guessed.
Use cursors/workspace references for large results instead of demanding one unlimited response.

## 5. Return, delivery, adoption and verification are separate

Track at least: tools actually called, candidates returned, full/source reads performed, scope
and unresolved coverage. Report host receipt only with its evidence; tool stdout is not proof
of host inclusion, and inclusion is not proof of answer benefit. Never turn unknown into zero.
Preserve conflicts and superseded versions. Assistant claims of completion remain assistant
claims until supported by an artifact, source or execution receipt.

On a failure, record the stage: catalog missing, connection/authorization failure, bad arguments,
bound-call failure, valid empty response, scope exclusion, omitted body, source gap or projection
failure. Correct arguments from the schema/error rather than silently dropping required fields.
At most one relevant guidance refresh for an execution failure; do not run a recursive repair loop.
Never print credentials. Do not change risk/module/relevance gates to manufacture a successful test.

## 6. Host-specific usage boundaries

| Surface | How to make EP discoverable | What remains unproved |
| --- | --- | --- |
| Codex desktop/CLI | Existing trusted MCP/Hook entry; inspect the current catalog and binding | A separate preparation profile is not a hot upgrade of an existing connection |
| Claude Code CLI | Reviewed CLI MCP registration and optional host-supported project rules referencing this guide | Native lifecycle/source capture is not certified by registration |
| Claude desktop local Code | Confirm tools inside that local Code session, not just in a separate CLI | Cloud/SSH sessions cannot inherit local process reachability by assumption |
| Claude Desktop ordinary Chat | Trusted local MCP configuration; attach/reference this guide if supported | No terminal/browser means it cannot install backend services itself |
| Hermes | Actual exposed compatible MCP/API surface and its supported task/project guidance | Do not assume its hooks, session files or receipt format match Codex |
| WorkBuddy | Review its prepared configuration and actual client approval flow | Prepared event parser or Hook name is not full native integration |
| Doubao Work | Select/enable the trusted plugin for the actual task; add this guide through a supported instruction/Skill mechanism | Plugin matching or a Skill cannot guarantee every-turn execution |
| Generic MCP / Windows / WSL / remote | Verify the actual schema and path/network mode separately | Localhost, paths, permissions and host receive evidence do not transfer automatically |

Instruction/Skill/project-rule loading is best effort unless native lifecycle evidence proves
otherwise. Do not overwrite existing rule files or create a Skill automatically just to embed this
guide. Rules improve tool selection; they do not create Hooks or enable capture.

## 7. Writes and optional experience feedback

New-host preparation profiles are read-only by default. Do not copy Codex retention hooks into
another host, import all old conversations, publish summaries, change operator preferences or
promote process candidates automatically. An agent may optionally produce a short, source-linked
failure→attempt→repair→verification note after a meaningful recovered detour; no per-task summary
is mandatory, and missing feedback must not break the existing memory pipeline. Submission requires
an exposed write tool, genuine identity, scope and user authorization; otherwise keep it as a local
task artifact, not a silently inserted fact or installed Skill.

## Copyable operating request

```text
Read this installation's docs/AGENT-USAGE.md and discover its actual MCP tools.
For this task, select personal history, conditional preferences, agent process experience
and/or external documents only when relevant; keep their evidence separate. Use current
genuine identity when available, never borrow or invent check_id. Resolve scenario ambiguity
before merging projects and read original sources when the requested detail needs them.
Report actual calls, returned evidence, original reads and remaining unknowns. Do not claim
automatic recording, delivery or answer adoption without receipts, or write memory/change
settings/register clients merely because this document exists. If a capability is missing,
state that boundary and continue only with permitted evidence.
```
