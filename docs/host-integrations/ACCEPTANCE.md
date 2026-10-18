# Host preparation acceptance / 宿主准备验收

Status: preparation implementation and scoped regression passed on macOS, 2026-10-18.
This is not full-host certification, a production deployment or a new release.

## Executed verification / 已执行验证

| Scope / 范围 | Actual result / 实际结果 |
| --- | --- |
| Host-adapter, guidance, status, Controller and scripts | 2,172 tests + 107 subtests passed |
| Offline host preparation subset (overlaps the above) | 89 passed |
| Existing API MCP focused routing/coercion suite | 62 passed |
| Console | 96 files, 666 tests passed |
| TypeScript / production standalone build | Passed / passed |
| Isolated stdio process | initialize/tools-list passed; 21 read-only tools, no knowledge/model calls |
| Optional HTTP transport | SDK initialize/list/call, auth, disabled-tool and session-cleanup checks passed in isolated fixtures |
| UI | Actual Chinese/English clicks, configuration preview, guidance, details, protocol feedback, refresh persistence and scroll checked |
| Responsive rendering | Native 1280px browser plus actual 390/768px iframe viewports; not physical mobile testing |

One independent final review raised five Important findings and one Minor regraded Important:
cross-host identity consumers, HTTP owner boundaries, session cleanup, configuration preservation,
Windows fixture classification and structured argument errors. All were fixed with targeted
RED-to-GREEN tests, followed by the scoped regression above. Later self-checks also covered
Windows GUI metadata discovery, UTF-8 transport, configuration freshness and accurate probe feedback.
The independent review predates those final self-check additions; it is not a second review of them.

No new provider calls were made for this preparation work. Mock/fixture tests and isolated EP
protocol probes do not prove model quality, Bank retrieval, host delivery or answer adoption.

## Preserved boundaries / 保留边界

- Native host tasks: deferred; no WorkBuddy installation, no Doubao task sent.
- Windows executor / prepared manual CI: not run.
- Automatic capture for new integrations: off; unknown source transports are not original evidence.
- Existing provider configuration, API keys, production memory/queues and Codex host registration: unchanged.
- Product version / GitHub publication / runtime deployment: unchanged, not performed here.

Read-only preparation does not silently replace any existing Codex integration. New-source capture
remains off, and source gaps remain incomplete. One optional HTTP gateway serves one EP data
owner; different owners require separate cores. Discovery uses configuration metadata fingerprints,
not credential-file content: ordinary edits invalidate observations, but adversarial edits preserving
metadata and hostile non-cooperative filesystem races are not certified.

Windows native registry/PowerShell/locking execution, actual client tasks, account availability,
automatic lifecycle capture, remote/TLS deployment, API/database/worker/model/service startup
and live production rollout are explicitly unverified. Missing Hooks are not invented; guidance
improves discovery but cannot force every-turn tool use. A generated matrix is documentary evidence.
