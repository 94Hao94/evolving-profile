# Connect a host: Codex, Claude Code and Claude Desktop

[简体中文](HOST-SETUP-中文.md) · [Backend first](DEPLOYMENT.md) · [Copyable Agent requests](AGENT-SETUP.md)

## What is verified, and what is a setup recipe?

Codex is the most exercised EP host. The public Python adapter can initialize
and expose user/agent tools in isolation. That does **not** certify a fresh
Claude installation's lifecycle, automatic capture, source parsing or delivery.
Claude recipes below follow the official host formats; native end-to-end
acceptance must be recorded on the target installation. No EP `.mcpb` package
or unified all-host one-click installer is included.

Use the [default `personal-memory` Bank and backend startup](DEPLOYMENT.md).
The examples assume API8888 and Controller12079. Substitute all related URLs
if you choose different ports. Register **one** EP adapter, never both the
current name and the legacy `hindsight_controller` alias.

## 1. Codex desktop or CLI: register the Controller tools

From the installed checkout, use a read-only `codex mcp list` first. If an EP
entry already exists, inspect it with `codex mcp get evolving_profile_controller`
and reconcile it after backup; do not overwrite or add a duplicate blindly.
For a new entry:

```bash
EP_DIR="$(pwd -P)"
codex mcp add evolving_profile_controller \
  --env EVOLVING_PROFILE_CONTROLLER_URL=http://127.0.0.1:12079 \
  --env EVOLVING_PROFILE_SOURCE_API_URL=http://127.0.0.1:8888 \
  --env EVOLVING_PROFILE_GUIDANCE_SRC="$EP_DIR/guidance" \
  --env EVOLVING_PROFILE_GUIDANCE_CONFIG="$HOME/.evolving-profile/guidance-v1/guidance-v1.json" \
  -- "$EP_DIR/api/.venv/bin/python" "$EP_DIR/host-adapter/evolving_profile_controller_mcp.py"
codex mcp list
```

Run that only at the checkout root after dependency installation. GUI apps may
not inherit your shell's PATH; the recorded executable/script paths must be
absolute. Codex MCP configuration normally lives in `~/.codex/config.toml`;
project configuration and managed policies can affect availability. Inspect the
desktop's MCP list and use a new conversation if its tool catalog has not refreshed.
Do not repeatedly restart the API to fix a host catalog cache.

After registration, request the real tool list. Expected entries include
`memory_check`, `user_preference`, `user_recall`, `user_research`, `agent_recall`,
`agent_research`, `search_scenario_summary`, `read_scenario_summary`, `read_source`.
Call `memory_check` for the current original prompt when a fresh binding is
needed, then use its returned check ID only in that prompt. Never invent or
reuse a prior prompt's ID. An empty new Bank is valid; fabricated hits are not.

## 2. Codex automatic lifecycle: review, merge and trust hooks

This is separate from MCP registration. Back up existing
`~/.codex/hooks.json`, project hooks and inline `[hooks]` tables. Codex merges
matching sources; adding the same handler twice can double capture. Preserve
unrelated handlers and use one representation per config layer.

For a **new** installation, create your own `~/.evolving-profile/codex.json`
with the fields below, using a local editor. Do not replace an existing file:

```json
{
  "evolvingProfileApiUrl": "http://127.0.0.1:12079",
  "bankId": "personal-memory",
  "agentName": "codex",
  "autoRecall": true,
  "autoRetain": true,
  "retainTokenThreshold": 12000,
  "retainTailMinAgeSeconds": 1800
}
```

Hooks and the dispatcher must share the same
configuration and queue. Capture only tasks the operator permits to be recorded.

The following is a **path template**, not a file to install unchanged. Replace
`/absolute/ep` with this installation's actual path; every command quotes paths.
Merge the event groups, do not replace the user's whole hook file:

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "\"/absolute/ep/api/.venv/bin/python\" \"/absolute/ep/host-adapter/session_start.py\"", "timeout": 15}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "\"/absolute/ep/api/.venv/bin/python\" \"/absolute/ep/host-adapter/recall.py\"", "timeout": 30}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "\"/absolute/ep/api/.venv/bin/python\" \"/absolute/ep/host-adapter/post_tool_use.py\"", "timeout": 15}]}],
    "PreCompact": [{"hooks": [{"type": "command", "command": "\"/absolute/ep/api/.venv/bin/python\" \"/absolute/ep/host-adapter/pre_compact.py\"", "timeout": 10}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "\"/absolute/ep/api/.venv/bin/python\" \"/absolute/ep/host-adapter/retain.py\"", "timeout": 45}]}]
  }
}
```

Keep Guidance config in its default absolute home location prepared in the
backend guide. Set required environment in a reviewed launch wrapper if changing
that location; a GUI does not inherit arbitrary terminal exports reliably.
Review/trust the exact definitions using Codex `/hooks` or the host's corresponding
review flow. New hashes may need trust again. This guide does not bypass trust or
permissions. Do not install `PreToolUse` denial gates or special per-session
canaries merely because they exist in the source tree.

Validate a natural prompt's ingress, context output and source identity; then a
permitted Stop capture and completed extraction. Token-batch capture is not
necessarily immediately submitted; threshold/tail-age settings intentionally
delay small batches. The [dispatcher](DEPLOYMENT.md#6-automatic-capture-extraction-and-optional-workers)
must be scheduled if using queued retention. Compaction checkpoint is recovery
navigation, not proof that a whole Session was summarized.

## 3. Claude Code CLI: explicit MCP tools first

Check `claude --version`, `claude mcp add --help` and `claude mcp list` locally.
Do not send a model request just to verify command syntax. For a new user-scoped
entry, run from the EP checkout:

```bash
EP_DIR="$(pwd -P)"
claude mcp add \
  --env EVOLVING_PROFILE_CONTROLLER_URL=http://127.0.0.1:12079 \
  --env EVOLVING_PROFILE_SOURCE_API_URL=http://127.0.0.1:8888 \
  --env EVOLVING_PROFILE_GUIDANCE_SRC="$EP_DIR/guidance" \
  --env EVOLVING_PROFILE_GUIDANCE_CONFIG="$HOME/.evolving-profile/guidance-v1/guidance-v1.json" \
  --transport stdio --scope user evolving_profile_controller \
  -- "$EP_DIR/api/.venv/bin/python" "$EP_DIR/host-adapter/evolving_profile_controller_mcp.py"
claude mcp list
```

`--transport` / `--scope` after the environment options prevents the server name
being consumed as another environment value. If your installed CLI syntax
differs, follow its help and preserve these same executable/arguments/environment.
Do not put API keys into shell history. In Claude Code use `/mcp` to inspect
connection/tools and perform a real scoped request with current binding.

For project-scoped setup use the official `.mcp.json` format and approval flow;
do not publish your machine's absolute paths or secrets in a shared repository.
User/local/project scope is a real choice; not every host uses identical precedence.

**Automatic Claude capture is not enabled by this recipe.** Claude Code has its
own `UserPromptSubmit`, `PostToolUse`, `Stop` and other hooks, but support for the
same event name does not prove EP's Codex transcript paths, turn IDs, source
qualification and queue logic are compatible. Do not copy all Codex hooks into
`~/.claude/settings.json`. A dedicated lifecycle bridge needs a recorded natural
task's source parsing, isolation, deduplication and receipt tests. Until then,
report explicit retrieval as available only after its test, automatic capture as
unverified. Running a Claude Code LLM Provider inside the backend is a different
feature and does not certify Claude as an EP host.

## 4. Claude Code desktop: the Code tab, local sessions

Choose **Code → Local**, using the intended machine/project. The current official
desktop supports shared CLI configuration, including `.mcp.json`, user MCP
settings and applicable hooks. Use the CLI registration above or a reviewed
equivalent in the app's connectors/settings UI; inspect the actual tool list
inside that Code session rather than assuming the standalone CLI result applies.

The desktop also loads `claude_desktop_config.json` servers into local Code
sessions. Duplicate names can use that definition in preference to CLI/project
definitions. Choose one authoritative EP entry and inspect all applicable
sources before adding another. Standalone CLI does not automatically read that
Desktop Chat file. Configuration rules can change; check the official reference.

A cloud/SSH session's `127.0.0.1` is **that remote environment**, not necessarily
your laptop. Local Python paths and local EP ports do not automatically work
there. This local guide does not certify cloud, SSH or WSL onboarding and does
not instruct public port exposure as a workaround. Automatic Claude lifecycle
limits from the CLI section still apply.

## 5. Claude Desktop: ordinary Chat, not the Code tab

Use the Desktop app's Developer/local-MCP configuration UI to locate its active
`claude_desktop_config.json`; on macOS it is commonly under
`~/Library/Application Support/Claude/`. Back it up and merge one `mcpServers`
entry, preserving unrelated entries. Example values must be replaced by actual
absolute paths; `$HOME` is not expanded inside a JSON string:

```json
{
  "mcpServers": {
    "evolving_profile_controller": {
      "command": "/absolute/ep/api/.venv/bin/python",
      "args": ["/absolute/ep/host-adapter/evolving_profile_controller_mcp.py"],
      "env": {
        "EVOLVING_PROFILE_CONTROLLER_URL": "http://127.0.0.1:12079",
        "EVOLVING_PROFILE_SOURCE_API_URL": "http://127.0.0.1:8888",
        "EVOLVING_PROFILE_GUIDANCE_SRC": "/absolute/ep/guidance",
        "EVOLVING_PROFILE_GUIDANCE_CONFIG": "/absolute/user-home/.evolving-profile/guidance-v1/guidance-v1.json"
      }
    }
  }
}
```

Refresh/restart the app after saving as required by that version, check its
connection log and conversation's connected tools, then test one explicit EP
read. A normal Chat without terminal/browser tools cannot install system
dependencies merely because you paste an installation request; use an authorized
CLI/Code agent for backend work and this surface for MCP reads.

The official Desktop Extensions route supports `.mcpb` packages, but EP does not
ship one here. Do not advertise a one-click EP extension. No automatic Chat
transcript capture, Claude Code Hook lifecycle or desktop history import is
certified by this MCP configuration.

## 6. A minimal host acceptance request

> Inspect the actual EP MCP tools available in this session. Establish a binding
> for this original prompt if needed. Read one task-relevant user or agent memory
> route, and use scenario/source tools only when the evidence gap requires them.
> Report tool names, returned count, source readback and observed delivery
> separately. A new empty Bank or unavailable route is a valid result; do not
> fabricate hits, reuse another prompt's check ID, write synthetic memories or
> claim complete automatic integration from a tools/list response.

Full acceptance is in [deployment](DEPLOYMENT.md#7-acceptance-and-troubleshooting).
Keep native host, server transport and application receipts separate.

## Official references, checked 2026-10-17

- [Codex MCP](https://developers.openai.com/codex/mcp), [Codex Hooks](https://developers.openai.com/codex/hooks)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp), [Hooks](https://code.claude.com/docs/en/hooks)
- [Claude Code desktop shared configuration](https://code.claude.com/docs/en/desktop#shared-configuration)
- [Claude Desktop local MCP and extensions](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)

These document host capabilities, not an EP end-to-end certification.
