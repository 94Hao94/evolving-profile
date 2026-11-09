# Host integration preparation

[简体中文](README-中文.md) · [Generated matrix](MATRIX.md) · [Windows](WINDOWS.md) · [Acceptance](ACCEPTANCE.md)

One EP core can serve multiple clients. This preparation layer distinguishes documented support,
configuration, isolated protocol checks and real-host evidence. It does not certify untested hosts.
The existing trusted Codex route is retained. New integrations are read-only; automatic capture is off.

## Inspect without changing client settings

From the EP source root on macOS, with the existing environment installed:

```bash
api/.venv/bin/python scripts/ep-host.py list --json
api/.venv/bin/python scripts/ep-host.py discover --json
api/.venv/bin/python scripts/ep-host.py doctor --host workbuddy --json
api/.venv/bin/python scripts/ep-host.py guide --host doubao_work --locale en --json
api/.venv/bin/python scripts/ep-host.py config-preview --host workbuddy --json
```

Discovery reads bounded application/configuration metadata, not private chats. `doctor` does not
start a client or service. Add `--probe` to run an isolated EP initialize/list check, not a memory query
or a native host task. The probe writes temporary subprocess state and a bounded preparation receipt
under the selected EP state root; it never certifies a real host. Refresh reuses that receipt only for
the matching host/platform/mode/version/code revision.
Configuration invalidation uses an explicitly labelled candidate-metadata fingerprint; discovery
does not read credential-bearing bytes. Reviewed apply/rollback uses full-byte revision hashes.

## Client setup routes

- Doubao Work: official documentation supports local STDIO and HTTP plugins. Prefer the prepared
  local command, args and environment for a local task. Its UI-managed settings remain manual import;
  no undocumented file path is guessed. Select the EP plugin/guide where available.
- WorkBuddy: official user-level MCP recipe is `.workbuddy/mcp.json`; generate a preview before
  modifying it. Hooks and transcript parsing still require native-host validation.
- Claude CLI, desktop local Code and ordinary Chat are distinct profiles. TOML, host-managed or
  unknown formats stay import-only when safe preservation cannot be guaranteed.
- Hermes and generic clients remain explicit capability checks, not automatically certified adapters.

Use the generated guide as advisory host instructions. Neither a Skill nor server instructions force
every turn to call EP. Read relevant history when needed; do not mechanically call every tool.
No-hook clients can query existing memory, but automatic capture and host-receive evidence may be unknown.

## Reviewed configuration changes (operator-only)

Automatic web writes are disabled in preparation mode. The CLI can save a JSON configuration plan:

```bash
api/.venv/bin/python scripts/ep-host.py config-preview --host workbuddy --save-plan --json
```

Review the exact target, interpreter, script, args, environment and before hash. Applying requires
`config-apply --host workbuddy --plan <saved_plan> --expected-sha256 <before_hash_or_absent> --confirm`.
Rollback requires `config-rollback --receipt <saved_receipt> --expected-sha256 <current_applied_hash> --confirm`.
Use the same host and state root. Only owned entries are replaceable; unrelated MCPs/Hooks survive.
Corrupt/duplicate-key configs, symlinks and concurrent edits are rejected. Prior content is backed up;
restoring an originally absent file moves the new file to a recoverable rollback path.
Do not put API credentials into a plan; use operator-owned references and review host expansion support.

## Optional governed HTTP MCP

The base API HTTP MCP is not the governed user/agent/preferences/scenario tool surface. The optional
`host-adapter/governed_mcp_http.py` reuses the installed MCP/FastMCP stack and isolated governed stdio
sessions, preserving tool names and enforcing execution permission even for direct hidden-tool calls.
It is not started by discovery or the installer. Bind loopback only; authentication is required even there.

Operator settings must contain `token_hashes` keyed by SHA256 of an operator-supplied bearer token;
each scope defines `owner_id`, `host_id`, `installation_id`, with an explicit absolute stdio `launch`.
Allowed Hosts/Origins are explicit. Keep settings private; no default token is shipped. Cross-owner
sessions never share a worker. One gateway launch serves one EP data owner: mixed-owner token
configuration is rejected, because separate processes alone do not isolate Bank authorization.
Different owners require separate governed cores. At most two sessions per owner/four total, 60-second idle cleanup and
30-second request timeout. Closed or expired sessions release their owner records and workers.
Network exposure needs a separate reviewed TLS/access design.
The preparation tests use FastMCP4.0.4; earlier framework capability support is not certified or made
a new global runtime floor. The existing API endpoint is unchanged.

## Verification and diagnosis

```bash
api/.venv/bin/python scripts/verify-host-integrations.py
api/.venv/bin/python scripts/ep-host.py export-diagnostics --host workbuddy --json
```

The focused suite uses synthetic temporary sources and isolated state. It makes no provider calls.
Shared diagnostic exports omit private content, headers, URL tokens and environment values.
See acceptance for actual runs; prepared CI is not an executed Windows result.
