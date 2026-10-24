# Claude Desktop and Claude CLI with Evolving Profile

Since 5.1.3, Evolving Profile ships a host-adaptive integration kit (`claude-code/`) that lets **Claude Desktop
(Cowork / local agent sessions)**, **Claude Code CLI** and **Codex** share one EP Bank. This page explains what it does,
how to install and verify it, how every piece fails, and what is *not* proven. [中文版](CLAUDE-DESKTOP-CLI-中文.md)

> Scope of evidence: developed and exercised on **one macOS machine** with Claude Desktop 3P (Cowork), a local EP install
> and a real Bank. The Claude **CLI** path was verified with simulated host markers (`CLAUDE_CODE_ENTRYPOINT=cli`) through
> the real bridge, **not** in a live CLI session. Windows and Linux are untested. See [Known limits](#known-limits).

## 1. What problem this solves

EP's hooks and storage were built around Codex. Pointing another host at them naively goes wrong in specific ways that
were each observed in practice:

| Symptom | Cause | What 5.1.3 does |
| --- | --- | --- |
| Claude Desktop chats never reach the Bank | Desktop sessions do not read `~/.claude/settings.json`; there is no hook entry point | A tiny **org plugin** declares the six lifecycle hooks and calls one bridge |
| Tool output (file dumps, `cat -n` listings, command results) stored as *"things the user said"* | The old CLI bridge flattened `tool_result` blocks into `user` text | The bridge keeps only human-visible dialogue: `tool_use`, `tool_result`, `thinking`, images, sidechains, system reminders are dropped |
| Recall context ignored by Claude | Old bridge printed a top-level `additionalContext` | Output is `{"hookSpecificOutput": {"hookEventName": …, "additionalContext": …}}` |
| Adapters could not tell hosts apart | Only `EVOLVING_PROFILE_AGENT_NAME` was set; adapters read `HINDSIGHT_AGENT_NAME` | Both are set, from automatic host detection |
| Desktop chats invisible to Scenario Summaries | The summary pipeline only reads Codex rollout files | `desktop_rollout.py` writes a Codex-shaped rollout into EP's own `claude-code/rollouts/` (never `~/.codex`) |
| Many fact-extraction batches quarantined | The model returns quotes that are *almost* verbatim; the validator rejects byte-inexactly; the retry resends the same input | Deterministic **quote repair** (below), fail-closed |
| ~4.3 KB of identical instructions injected every prompt | Hook re-sends the memory-use instruction each turn | Sent in full at SessionStart, replaced by a one-line stub afterwards |

## 2. Architecture

```
Claude Desktop (Cowork) ──org plugin──┐
Claude Code CLI ─ ~/.claude/settings ─┼─► hook_bridge_desktop.py ─► host-adapter/{session_start,recall,pre_tool_use,
Codex (unchanged, own hooks) ─────────┘     detect_host()              post_tool_use,pre_compact,retain}.py ─► EP API / Bank
                                            normalize_transcript()
                                            desktop_rollout.py ─► claude-code/rollouts/ ─► Scenario Summary pipeline
```

* **`hook_bridge_desktop.py`** – the single entry point. `python hook_bridge_desktop.py <session|recall|pretool|posttool|precompact|retain>`.
  It never blocks Claude: every failure is logged to `claude-code/desktop-hook.log` (event, payload *keys*, duration, exit code – no content) and the
  process exits 0. PreToolUse never emits allow/deny decisions.
* **`hook_bridge.py`** – a `runpy` shim to the file above, so older CLI configurations that still name `hook_bridge.py` get the fixed behaviour.
* **`desktop_rollout.py`** – transcript → Codex-format rollout with a **20-minute settle period**: rewriting a rollout while the background
  summariser works on it invalidates its job, so updates are deferred (marker in `rollouts-pending/`) and flushed on a later session/prompt/stop once the
  file has been quiet. Scheduler-wrapper sessions (`<scheduled-task`, `[SCHEDULED TASK - AUTOMATED FIRING`) are skipped. Kill switch: create `claude-code/desktop-rollout.off`.
* **`compat/desktop_compat_patches.py`** – four small idempotent in-place edits of `host-adapter/` (already applied in this release; the tool exists so an older install can be upgraded and so `check` can detect an EP upgrade that silently reverted them):

  | File | Change | Why |
  | --- | --- | --- |
  | `retain.py` | queue items carry `origin_agent` from `HINDSIGHT_AGENT_NAME` (default `codex`) | tell hosts apart at capture |
  | `retention_worker.py` | `origin_agent` is copied to Bank metadata | same, on the Bank side |
  | `recall.py` | prompt-ingress `host_id` comes from the same variable | recall receipts per host |
  | `lib/session_paths.py` | adds `claude-code/rollouts` to the Codex-layout session roots | Scenario Summaries can see Claude chats |

  Deliberately **not** changed: the `codex-hook-token-batch` / `codex-batch-` / `codex-userpromptsubmit` identifiers, because other EP code keys on them. Existing Codex data keeps `origin_agent=codex`.

### Host detection (`detect_host()`)

| Order | Signal | Result |
| --- | --- | --- |
| 1 | env `EP_HOST` (letters, digits, `-`, `_`; ≤ 40 chars) | that value (manual override / a new host) |
| 2 | `CLAUDE_CODE_IS_COWORK=1`, or `CLAUDE_CODE_ENTRYPOINT` ∈ `local-agent`, `claude-desktop`, `desktop` | `claude-desktop` |
| 3 | `CLAUDE_CODE_ENTRYPOINT=cli` | `claude-cli` |
| 4 | anything else (SDK, IDE, future values) | `claude-code` – and the raw entrypoint is logged so the health check can tell you to add a rule |

The result is written to `origin_agent` in the Bank, to `host_id` in recall receipts and to the `host` field in the hook log.

## 3. Install

Prerequisites: a working EP 5.1 install (API on `127.0.0.1:12079`), Python 3, and – for Desktop only – `sudo` once.

```bash
# from a checkout of this repository
zsh claude-code/install.sh --dry-run               # prints every step, changes nothing
zsh claude-code/install.sh                         # kit + host-adapter edits + CLI hooks            (no sudo)
zsh claude-code/install.sh --desktop-plugin        # ... plus the Claude Desktop plugin              (sudo once)
```

What it does, in order (`EP_HOME` defaults to `~/.evolving-profile`):

1. copies `claude-code/` to `$EP_HOME/claude-code/` (existing logs, rollouts and transcripts are kept);
2. applies the four host-adapter edits to `$EP_HOME/runtime/host-adapter` (skips files already patched, **refuses** files whose surrounding code changed – those need a human; backups `*.pre-reapply-<timestamp>`);
3. if `EP_API_SRC=<api source dir>` is set, applies the quote-repair patch to the API source (this repository already contains it);
4. merges the EP hooks into `~/.claude/settings.json` (backup `settings.json.pre-ep-<timestamp>`; unrelated keys and other people's hooks are preserved; unparseable files are never overwritten);
5. with `--desktop-plugin`: renders `desktop-plugin/ep-desktop-bridge/hooks/hooks.json` with your Python and bridge paths and copies it to
   `/Library/Application Support/Claude/org-plugins/ep-desktop-bridge` (previous copy backed up as `.bak-<timestamp>`; files are made world-readable, otherwise the non-root Desktop app cannot load them).

Then **quit Claude Desktop (Cmd+Q), reopen it and start a new session** – plugins load at session start.

`zsh claude-code/install.sh --uninstall [--desktop-plugin]` removes the CLI hooks (and the plugin). Restart services after upgrading EP code:
`launchctl kickstart -k gui/$(id -u)/com.evolving-profile.api-shadow` (service names depend on your setup).

Codex is not touched by any step: `~/.codex/*` and `codex.json` are neither read nor written.

### Add the MCP servers (reads)

Hooks cover *capture and per-prompt context*. Active reads (`user_recall`, `user_research`, …) need the EP MCP server registered in the host – see
[HOST-SETUP.md](../HOST-SETUP.md) and the [host matrix](MATRIX.md). Claude Desktop (3P) takes it from its `mcpServers` config.

## 4. Verify

```bash
python3 claude-code/compat/ep_desktop_health.py          # read-only; exit 1 only on FAIL
python3 claude-code/compat/ep_desktop_health.py --json
```

Checks (each `OK` / `WARN` / `FAIL`): API `/health`; compat patches intact; bridge files compile; Desktop plugin present with 6/6 events; hook activity in the last 24 h; rollouts and
pending markers; write-queue (quarantined **Claude Desktop** items are a `FAIL`, other hosts' quarantined items a `WARN`); recall-receipt `host_id`; Scenario-Summary jobs for Claude sessions; worker error logs;
**read/write embedding-model consistency**; and which Claude hosts reached EP in 24 h (so a new, unrecognised entrypoint becomes visible).

`WARN` means look at it, `FAIL` means a link in the chain is broken. `functional_status: degraded` on `/health` only mirrors the *most recent* request and resets on the next success.

Quick manual proof that hooks fire: `tail -n 5 $EP_HOME/claude-code/desktop-hook.log` after a prompt – new lines with `"host": "claude-desktop"` (or `claude-cli`).

### Tests

```bash
EP_ADAPTER=$PWD/host-adapter zsh claude-code/compat/run_tests.sh      # from a checkout
zsh claude-code/compat/run_tests.sh                                   # against an installed EP
```

Runs on a **staged copy** with an isolated `HOME`; nothing live is modified. It checks the patches, then the compat tests (patcher, origin tagging, desktop roots, settle period, host-id label,
automated-session skipping, quote repair, host detection matrix, tool-result regression, instruction de-duplication, CLI-hook installer), then EP's own retention suites.
Result recorded for this release: see [RELEASE-NOTES-5.1.3.md](../RELEASE-NOTES-5.1.3.md).

## 5. Fact-extraction quote repair

EP only stores a fact if its `source_quote` is an exact substring of the *claimed author's* original message. Models often retype a quote with small drift, or use the wrong
`source_message_index`; the batch then fails and is retried with identical input until it is quarantined. The patch (`source_attribution.py`) tries two **deterministic** repairs before the exact check:

1. `exact_quote_index_corrected` – the quote is verbatim in exactly one message of the claimed role, just not at the stated index;
2. `snapped_to_verbatim_span` – the quote is ≥ 0.90 similar to **one** span (unique, runner-up at least 0.10 lower) of a message of the claimed role; the span itself is stored, not the model's text.

Never relaxed: author/role, ambiguity (fails closed), the `source_quote_ref` selector path, anything below the thresholds, spans polluted by pasted `cat -n` line numbers, quotes > 1,500 characters. Provenance is recorded in
`source_quote_resolution` / `source_quote_repair`. Kill switch: `EVOLVING_PROFILE_API_QUOTE_REPAIR=0` (read per call). In the first measurement 87 % of rejected near-miss quotes were ≥ 0.90 similar to a unique span; the *long-term* effect on the quarantine rate has not been measured yet.

## 6. Operations notes learned the hard way

* **Embedding split.** If the API launcher loads a retrieval-model overlay but the worker launcher does not, new vectors are written in one space and queried in another; hybrid retrieval still "works" through lexical/graph arms, so nothing visibly crashes. The health check compares the model each process logged at start-up and reports `FAIL` on mismatch (measured on a real Bank: vector-only top-1 0.01 mismatched vs 0.94 consistent – an easy task that shows the mismatch, not absolute quality). `compat/fix_embedding_split.sh status|apply|rollback` handles the overlay case.
* **LLM failover.** The API supports numbered extra providers plus a strategy. Example for an OpenAI-compatible endpoint with several models (same key):

  ```
  EVOLVING_PROFILE_API_LLM_1_PROVIDER=openai   EVOLVING_PROFILE_API_LLM_1_API_KEY=…   EVOLVING_PROFILE_API_LLM_1_BASE_URL=…   EVOLVING_PROFILE_API_LLM_1_MODEL=<fallback model>
  EVOLVING_PROFILE_API_LLM_STRATEGY='{"mode":"failover"}'
  ```

  Quote the JSON: launchers `source` the profile in zsh, and an unquoted `{"mode": "failover"}` is a parse error. Models on one endpoint protect against a single model failing, not against the endpoint being down.
* **Claude's ~60 s per-MCP-call limit.** Long host-side work must be a background job that is polled, not a long synchronous call.
* **Facts misattributed by the old bridge.** Bank rows whose `source_quote` occurs only inside a `tool_result` of the raw Claude session (never in human-typed text) can be re-labelled instead of deleted: keep the original metadata in a backup file, then set `statement_kind` to `source_repetition` and `independent_user_evidence` to `false`, recording the previous values. This kit does not ship that one-off tool; the approach is reversible by restoring the saved metadata.
* **Rollback.** Every edit leaves `*.pre-<name>-<timestamp>` next to the file. Stop Claude chats from reaching Scenario Summaries only: `touch $EP_HOME/claude-code/desktop-rollout.off`. Restore full per-prompt instruction text: `EP_FULL_INSTRUCTION=1`.

## 7. Known limits

* **CLI**: verified through the real bridge with simulated host markers, not in a live CLI session.
* **Desktop plugin** needs `sudo` once (system plugin directory) and a Desktop restart; it only affects sessions started afterwards.
* All Desktop (Cowork) chats share one working directory (`/private/var/empty`), so Scenario Summaries cannot group them by project.
* Desktop rollouts reach Scenario Summaries after the settle period, not instantly.
* The quote repair reduces, but does not eliminate, quarantined batches (very long chunks can still exceed the extraction budget).
* The instruction de-duplication takes effect for sessions that started after it was installed.
* Hook activity proves delivery of context, not that an answer used it.
* macOS only; Windows/Linux paths are untested.
