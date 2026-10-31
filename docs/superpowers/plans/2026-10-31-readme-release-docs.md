# EP 5.1.4 README 与部署文档校准 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 校准 EP 5.1.4 的版本、双语 README、宿主命名和完整部署路径，使新读者能从首屏到健康验收完成真实安装。

**Architecture:** 以根 `VERSION` 和当前脚本为事实源，先改 README 双语结构，再同步部署文档与直接误导安装的旧版本引用，最后用脚本和链接扫描验证。

**Tech Stack:** Markdown, shell/Python release preflight, existing EP installer and docs.

**Spec:** `docs/superpowers/specs/2026-10-31-readme-release-docs-design.md`

## Global Constraints

- 产品版本为 `5.1.4`，根 `VERSION` 是唯一权威版本源。
- `Claude Desktop`（普通 Chat/Cowork）与 `Claude Code`（CLI/桌面 Code 页）必须分开称呼。
- 当前仓库的 `release/5.1.4` 和 `v5.1.4` 是有效安装入口；旧 RC/旧贡献分支不能作为当前指引。
- 示例对话是 illustrative，不是质量基准或收益保证。

## Review Focus

- README 首屏是否能在第一次阅读时找到中文入口、价值差异和真实快速开始。
- Windows/云端/远程能力是否仍被文档误读为已认证。
- Claude Desktop 普通 Chat、Claude Desktop Cowork 和 Claude Code 桌面 Code 页是否被错误合并。
- 部署命令中的目录、端口、环境变量和健康检查是否与脚本一致。
- 备份/恢复、升级/回退和云备份开关是否明确区分“配置显示”与“实际执行”。

### Task 1: Rewrite bilingual README entry and value proof

**Files:** `README.md`, `README-中文.md`

- [x] Fix title-adjacent language links and release links.
- [x] Add clearly marked before/after comparison with short simulated conversations.
- [x] Add a deployment decision path and first-reader checklist.
- [x] Normalize host names and state the distinction in one sentence.
- [x] Remove stale branch/RC instructions and review every link/heading.

### Task 2: Synchronize deployment guides and stale host setup references

**Files:** `docs/DEPLOYMENT.md`, `docs/DEPLOYMENT-中文.md`, `docs/AGENT-SETUP.md`, `docs/AGENT-SETUP-中文.md`

- [x] Replace stale version/branch claims with current-version source-of-truth wording.
- [x] Add explicit local deployment path, ports, health checks, backup/restore and upgrade/rollback checklist.
- [x] Normalize Claude host naming without changing actual commands.

### Task 3: Verify and publish the documentation change

- [x] Run `python3 scripts/release-preflight.py`.
- [x] Run `bash scripts/verify-package.sh` and focused documentation/version tests.
- [x] Scan for stale `release/5.1.0`, `v5.1.2-rc.1`, and ambiguous `Claude Code desktop` labels.
- [ ] Inspect the diff and commit the documentation release.
