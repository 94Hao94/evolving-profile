# Evolving Profile 5.1.3

> English release notes first. 中文更新说明见本文后半部分。

Release date: 2026-10-24 (contribution branch preparation)
Status: **local draft pushed to the personal fork branch `release/5.1.3`; no upstream PR, tag or GitHub Release has been created** (tracked separately in the [release ledger](RELEASE-LEDGER.md)).

## Problems solved

EP's capture hooks and storage were built around Codex. Attaching Claude Desktop and Claude CLI to the same Bank exposed concrete problems (each observed on a real install):

1. Claude Desktop sessions had no hook entry point, so desktop chats never reached the Bank or the Scenario Summaries.
2. The earlier Claude CLI bridge stored `tool_result` blocks (file dumps, `cat -n` listings, command output) as **user** speech, which then produced Bank facts attributed to the user that the user never said; it also printed `additionalContext` in a shape Claude ignores and set only one of the two agent-name variables the adapters read.
3. Fact extraction batches were quarantined in bulk because model-returned `source_quote`s were almost, but not byte-for-byte, verbatim.
4. About 4.3 KB of identical memory-use instructions were re-injected on every prompt.
5. A read/write embedding-model split could go unnoticed (API read with one model while the worker wrote with another).

## What changed

* **`claude-code/`** (new): host-aware bridge `hook_bridge_desktop.py` (+ `hook_bridge.py` shim), `desktop_rollout.py`, `install.sh`, `install_cli_hooks.py`, `install-desktop-plugin.sh`, desktop plugin template, `compat/` (patcher, quote-repair patcher, health check, embedding-split helper, test runner, 10 test modules).
  Hosts are detected (`claude-desktop`, `claude-cli`, generic `claude-code`; `EP_HOST` overrides) and recorded as `origin_agent` / `host_id`. The bridge never blocks Claude (always exit 0, content-free diagnostic log).
* **`host-adapter/`**: four small edits – `retain.py` and `retention_worker.py` carry `origin_agent`; `recall.py` takes `host_id` from the agent-name variable; `lib/session_paths.py` adds `claude-code/rollouts` as a session root. Applied by `desktop_compat_patches.py` onto the 5.1.2 files (the diff against 5.1.2 is 4 files, about a dozen lines).
* **`api/…/engine/retain/source_attribution.py`**: two deterministic, fail-closed quote repairs (`exact_quote_index_corrected`, `snapped_to_verbatim_span`; ≥ 0.90 similarity to a unique span with a 0.10 margin; role-bound; line-number-polluted spans and quotes > 1,500 characters excluded). Kill switch `EVOLVING_PROFILE_API_QUOTE_REPAIR=0`.
* Instruction de-duplication in the bridge (full text at SessionStart, one-line stub afterwards; `EP_FULL_INSTRUCTION=1` restores the old behaviour).
* Documentation: [Claude Desktop and Claude CLI guide](host-integrations/CLAUDE-DESKTOP-CLI.md) ([中文](host-integrations/CLAUDE-DESKTOP-CLI-中文.md)), README host table and section, this file.
* `VERSION` 5.1.3, `config/release-manifest.json` build `ep513-claude-hosts`, NOTICE line, CHANGELOG-5.1.

Not changed: Codex hooks and data, `~/.codex`, `codex.json`, the `codex-hook-token-batch` / `codex-batch-` identifiers, Console, MCP tool contracts, retrieval thresholds, the generated host matrix (it still lists Claude hosts as "not natively tested" – that registry records documented capability, not this kit's local evidence).

## Upgrade and rollback

New installs of this package already contain every edit. For an existing install:

```bash
zsh claude-code/install.sh --dry-run
zsh claude-code/install.sh [--desktop-plugin]        # --desktop-plugin needs sudo once; then Cmd+Q and reopen Claude Desktop
python3 claude-code/compat/ep_desktop_health.py
```

Edits leave `*.pre-reapply-<ts>` / `settings.json.pre-ep-<ts>` / `.bak-<ts>` backups. `install.sh --uninstall [--desktop-plugin]` removes the hooks; `touch claude-code/desktop-rollout.off` stops Claude chats feeding Scenario Summaries; the two kill switches above disable quote repair and de-duplication. No database migration; no Bank data is rewritten by this package. Restart the API and workers after replacing `host-adapter/` or `api/` code. Already-open Claude sessions keep the old context until restarted.

## Known limits

* Exercised on **one macOS machine** with Claude Desktop 3P (Cowork). The **CLI** path was verified through the real bridge with simulated host markers (`CLAUDE_CODE_ENTRYPOINT=cli`), not in a live CLI session. Windows/Linux untested.
* All Desktop chats share one working directory, so Scenario Summaries cannot group them by project; their rollouts appear only after a 20-minute settle period.
* Hook activity proves context delivery, not that an answer used it. No answer-quality or recall-rate benefit is claimed.
* Quote repair lowers but does not eliminate quarantined batches (very long chunks can still exceed the extraction budget). Its effect on the long-term quarantine rate has not been measured.
* The one-off clean-up of Bank rows misattributed by the old bridge was done on the author's Bank with a private script that is **not** included; the guide describes the reversible approach.
* Release scripts do not prove front-end behaviour, Bank migration, MCP delivery in every host, or a GitHub Release.

## Verification

All numbers are from runs on 2026-10-24 on the author's macOS machine.

| Scope | Command or real readback | Result |
| --- | --- | --- |
| Claude kit tests against this package's `host-adapter/` | `EP_ADAPTER=$PWD/host-adapter zsh claude-code/compat/run_tests.sh` | patches intact (4/4); **97 compat tests OK (1 skipped)**; **30 EP retention tests OK** |
| Same kit against the author's live install | `zsh claude-code/compat/run_tests.sh` | 95 compat + 29 retention OK (run before the installer tests were added; live adapter has no `route_external_hook`, so it is a different base from this package) |
| Patcher fidelity | patcher applied to pristine 5.1.2 `host-adapter` files = shipped files | byte-identical (`cmp`), second apply is a no-op |
| Installer | temporary `EP_HOME` and `HOME`: `install.sh` dry-run and real run; `install_cli_hooks.py` unit tests | OK; 5 installer unit tests (create file and register 6 events; keep foreign keys/hooks and stay idempotent; uninstall removes only EP entries; dry-run changes nothing and real runs back up; unparseable settings are never overwritten) |
| Release preflight | `python3 scripts/release-preflight.py --json`; `python3 -m unittest scripts/test_release_preflight.py` | passed (5.1.3); 8 tests OK |
| Package check | `./scripts/verify-package.sh` | passed; secret/personal-data scan: 1,795 text files, 0 findings |
| Host-adapter full suite (regression guard) | `unittest discover` under an isolated `HOME`, 5.1.2 tree vs this tree | identical result in both: 520 run, 1 failure + 115 errors that come from the isolated environment; **no test fails only in this tree**. This is *not* a pass claim for the whole suite |
| Real chain on the author's machine | `ep_desktop_health.py` | 11 OK, 1 WARN (failed Scenario-Summary jobs of automated sessions); ~700 hook events in 24 h, 0 problem rows; Desktop chats stored with `origin_agent=claude-desktop`; Desktop sessions summarised |

Not run: Console tests/build (no Console change), API-wide test suite, Windows, a live Claude CLI session, any benefit measurement.

## Authors and acknowledgements

Unchanged from [NOTICE](../NOTICE.md): EP is developed on top of Hindsight (vectorize-io/hindsight); the distribution author is CCY. Git commit identities are recorded by `release-preflight.py` and are not a contributor audit.

## GitHub status

* Upstream: `https://github.com/94Hao94/evolving-profile-2.2` (`origin`); personal fork: `https://github.com/ccygod/evolving-profile-2.2` (`fork`).
* Branch: `release/5.1.3` (based on `release/5.1.2-rc.1`, which has open PR #6); commit SHA recorded in the ledger after push.
* PR: not created. Tag: not created. Release: not published.

---

# Evolving Profile 5.1.3 中文更新说明

状态：本地草稿，已推送到个人 fork 的 `release/5.1.3` 分支；**未创建上游 PR、Tag 或 GitHub Release**。

**解决的问题：** 让 Claude Desktop 和 Claude CLI 与 Codex 共用同一个 EP Bank。实际安装上观察到的问题包括：Desktop 没有钩子入口、旧 CLI 桥把工具输出当成“用户说的话”入库、
模型返回的引文差一点点就导致整批事实提炼被隔离、每轮重复注入约 4.3 KB 相同说明、读写嵌入模型分裂无人察觉。

**主要变化：** 新增 `claude-code/` 套件（按宿主自适应的桥接脚本、桌面 rollout 转换、安装器、Desktop 插件模板、补丁器、健康检查、测试）；`host-adapter/` 四处小改动；
`source_attribution.py` 的确定性引文修复；说明去重；中英文指南与 README 章节。**不改** Codex、`~/.codex`、`codex.json`、Console、MCP 工具契约和检索阈值。

**升级与回退：** `zsh claude-code/install.sh --dry-run`，再 `zsh claude-code/install.sh [--desktop-plugin]`（Desktop 插件需一次 sudo，之后 Cmd+Q 重开）；用 `ep_desktop_health.py` 检查。所有改动都有备份，`--uninstall` 可移除，
`desktop-rollout.off`、`EVOLVING_PROFILE_API_QUOTE_REPAIR=0`、`EP_FULL_INSTRUCTION=1` 分别是三个关闭开关。无数据库迁移，本包不会改写 Bank 数据。

**已知边界：** 仅在一台 macOS 上运行；CLI 一路只用模拟宿主标记经真实桥接脚本验证，未做真实 CLI 会话；Windows/Linux 未测；Desktop 对话共用一个工作目录，无法按项目分组，rollout 要过 20 分钟静置期；
钩子有活动不等于回答用到了上下文，不宣称回答质量或召回率收益；引文修复只能减少、不能消除隔离，长期隔离率尚未测量；清理旧桥错误归属事实用的是作者本机的私有脚本，未随附。

**验证（2026-10-24，作者本机）：** 套件测试对本包 `host-adapter/`：补丁 4/4 完整，兼容测试 97 条通过（1 条跳过），EP 写入重试测试 30 条通过；补丁器施加到 5.1.2 原文件后与随包文件逐字节一致，二次应用无变化；
安装器在临时目录里 dry-run 和真实运行通过，安装器单元测试 5 条通过；`release-preflight` 通过（5.1.3），8 条测试通过；`verify-package.sh` 通过，秘密/个人信息扫描 1,795 个文本文件 0 发现；
host-adapter 全量在隔离 HOME 下新旧两棵树结果完全相同（520 条，1 失败 + 115 错误均来自隔离环境），**没有只在本树失败的测试**——这不是全量通过的声明；
真实链路健康检查 11 项 OK、1 项 WARN。未运行：Console 测试/构建、API 全量测试、Windows、真实 CLI 会话、任何收益测量。
