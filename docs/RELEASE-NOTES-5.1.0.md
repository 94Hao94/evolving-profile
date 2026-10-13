# Evolving Profile 5.1.0 — Release Notes

发布日期：2026-10-10  
状态：PR #4 已提交；尚未合并、打 Tag 或创建 GitHub Release

## 解决的问题

5.1 解决 EP5.0 在长 Session、来源覆盖、Agent Research 投影和原生复核可见性
方面的边界问题，同时保持“候选不等于事实、工具调用不等于答案采用”的证据边界。

## 本次变更

- 长 Session 使用同轮安全的确定性分段，避免单个摘要承载过多用户条件。
- 标准/完整 Session 摘要预算提高；紧凑层仍保持轻量。
- Provider 状态草稿失败时生成源绑定候选，但必须通过独立覆盖审查和 CAS 才能发布。
- 纠正、约束、已答复请求和助手报告分别绑定真实来源与字段；合并投影不能生成原句。
- Native source review 使用独立非 HTTP provenance，未知模型身份不被伪造。
- Agent Research 嵌套回执解包和节点计数投影保持父子独立。
- 新增脱敏发行配图和 `scripts/install-ep51.sh` 一键本地部署入口。
- 公开文档补充 Codex、Claude Code、Hermes 的适配现状与下一版本增强边界；中文 README 使用本地化图示和数据丰富链路/回执截图。

## 升级与回退

1. 先备份 Bank、运行配置、Guidance Registry、RAG 索引签名和审计回执。
2. 从新分支执行 `./scripts/install-ep51.sh --mode local --no-launch`，填入自己的 `.env`。
3. 需要运行 API/Console 时，按 `api/README.md` 和 Console 配置启动；安装器不会自动打开 JEV、外部 RAG、云备份或复制生产记忆。
4. 回退到 5.0 时恢复上一分支和配置快照；过程记忆为独立平面，可按策略保留。

## 已知边界

- 工具回执可证明调用、返回、送达和原文回读，不保证黑盒 Agent 在最终回答中采用了候选。
- 旧长会话 `01a123a0-aa87-7cf2-a2bf-a1b8c969c3f7` 与 `01a123e6-6237-77c0-a194-69a426ba9d34` 的真实恢复仍遵守安全拒绝门：Provider 覆盖或预算不足时保留原文，不强行发布摘要。
- Native 复核可以是真实独立 Agent 复核，但宿主未暴露的精确模型身份保持 unknown。
- 本文件的 GitHub PR、合并、Tag、Release 状态要以发布后回读为准。

## 验证

| 范围 | 命令或真实读回 | 结果 | 时间 |
| --- | --- | --- | --- |
| 发行包预检 | `python3 scripts/release-preflight.py --json` | 通过；5.1.0、分支/远端/作者快照已读回 | 2026-10-10 |
| 脱敏扫描 | `./scripts/verify-package.sh` | 通过；无个人 Bank、API Key 或个人路径命中 | 2026-10-10 |
| 情境状态/覆盖 | `pytest host-adapter/test_scenario_state_v3.py host-adapter/test_memory_recovery_scenario.py host-adapter/test_scenario_episode_model.py host-adapter/test_scenario_episodes.py host-adapter/test_scenario_validation_feedback.py host-adapter/test_context_incremental.py` | 166 passed | 2026-10-10 |
| Console/TypeScript/build | `npm test -w @evolving-profile/console -- --run`; `npx tsc --noEmit -p console/tsconfig.json`; `npm run build -w @evolving-profile/console` | 78 files / 531 tests passed；TypeScript 通过；生产与 standalone 构建通过 | 2026-10-10 |
| 一键部署 | `./scripts/install-ep51.sh --mode local --skip-deps --no-launch` | 预检、脱敏、构建和本地 manifest 通过；未启动服务 | 2026-10-10 |
| 依赖安全 | `npm audit --omit=dev` | 关键漏洞 0；仍有 8 个高/中等级依赖告警，已记录，不宣称零漏洞 | 2026-10-10 |
| 浏览器/拓扑 | 真实 Prompt、节点详情、Agent Research、滚动和多语言截图 | 已有开发运行证据；发行包需回读 | 2026-10-10 |
| GitHub 状态 | 分支、PR、Tag、Release 回读 | 未执行 | 2026-10-10 |

## 作者与致谢

沿用 [`NOTICE.md`](../NOTICE.md) 的 CCY 发行署名和 Hindsight 致谢边界。Git 提交
作者、仓库拥有者、EP 发行作者和上游项目致谢不自动合并为同一身份。

## GitHub 状态

- 上游仓库：`https://github.com/94Hao94/evolving-profile`
- 脱敏发行仓库：`https://github.com/ccygod/evolving-profile-2.2`
- 分支：`release/5.1.0`（fork 已推送）
- PR：[上游 PR #4](https://github.com/94Hao94/evolving-profile/pull/4)
- Tag：个人 fork 已创建 `v5.1.0-rc.2`
- GitHub Release：[Evolving Profile 5.1.0-rc.2](https://github.com/ccygod/evolving-profile-2.2/releases/tag/v5.1.0-rc.2)，预发布状态

## 来源与署名边界

- 个人发行渠道：[`ccygod/evolving-profile-2.2`](https://github.com/ccygod/evolving-profile-2.2)，分支 `release/5.1.0`。
- 上游协作渠道：[`94Hao94/evolving-profile`](https://github.com/94Hao94/evolving-profile)，PR [#4](https://github.com/94Hao94/evolving-profile/pull/4)。
- 两者来自同一 EP 5.1 发行分支；个人 fork 用于自有发布和备份，上游 PR 用于贡献协作。
- `NOTICE.md` 的公开发行作者/维护者署名为 CCY；GitHub 账号、仓库拥有者、上游项目拥有者和本机 Git 提交身份不自动等同。

## 2026-10-13 retention hotfix / 后台写入热修复

### Exact-quote recovery and overview follow-up

Content-quality retries now provide deterministic, bounded exact-source quote
selectors. A selector is accepted only when the current chunk, role, message
index and source offsets match; quote rewriting and stitching remain invalid.
The original exact-quote route still works, and partial catalog coverage does
not imply that uncatalogued source text is absent. Retry count and concurrency
settings are unchanged; the catalog adds bounded input only on an existing
quality retry, not on every normal extraction.

The overview uses explicit `parent_operation_id` evidence to group batch failures
without guessing from text, time or document similarity. It exposes current-Bank
queue metadata and host-global dispatcher freshness separately, keeps historical
failures visible after recovery, and represents a brief refresh with a fresh
published map as updating rather than a false outage. All ten locale catalogs
include the new UI messages.

Scoped local recovery requires a freshly read completed operation receipt plus
unchanged full-row fingerprints. A concurrent source change, a wrong Bank or
operation, or an incomplete snapshot blocks reconciliation. Only the matching
completed rows are removed; new captures and other Banks are retained.

Follow-up migration: upgrade the API/worker and Console together. Back up the
queue and original failure receipts before retrying the original operation;
after actual completion, reconcile only its unchanged quarantined snapshot.
Do not reset local counters or overwrite the queue with an old backup. Rollback
restores the prior code/build, not a stale queue over completed or new writes.

Fresh follow-up verification (2026-10-13): Host/Guidance/Status/Controller **1203
passed + 107 subtests**; scoped API extraction, attribution, retry, chunking and
lineage projection **229 passed**; Console **78 files / 546 passed**; TypeScript,
production/standalone build, release preflight and package scanning passed.
Actual original-operation retries completed, with non-empty source memories,
and scoped quarantine reconciliation completed. Chinese/English UI language
switching, refresh, history expansion and a 390px viewport were checked on the
deployed build. This is not a claim that every API integration test or every
future provider response succeeds. The RC tag remains unchanged; the fix is
distributed through the existing release branch and upstream PR.

本次后续修复既解决引用重试的根因，也区分真实失败、隔离记录、主机调度状态和
历史失败尝试。模型仍可能返回不合格引用或遇到超时；此时保持原文保护和失败隔离，
不放松事实/来源核验。真实恢复、运行页面和发行包测试均已分别核对。

Source envelopes are bounded by the configured structured cap instead of being
clamped to the smaller prose chunk target. No source/authority fields are dropped.
Terminal retry and policy failures are durably quarantined with raw content and
the prior operation/batch/submission lineage preserved; other eligible batches
continue. Ordinary rescans do not release quarantine, and completion remains the
only event that removes raw queue items.

Migration: back up the local queue, dispatcher state and source files. Upgrade
the API extraction code and background dispatcher together. Restart the
extraction worker to load the new code; the periodic dispatcher loads its update
on the next run. For a previously failed operation, preflight its source with the
resolved Bank budgets, then explicitly retry its original operation ID. Keep
old failure evidence; do not reset counters or submit the same content under a
new identity. Quarantine does not mean successful extraction or data deletion.

Model schema/source-quote failures and provider timeouts remain possible during
backlog processing. They retain bounded retries and terminal quarantine; this
hotfix does not weaken source verification or promise every model extraction
will succeed. Accumulated queues drain asynchronously under existing settings.

Rollback: restore the backed-up source and worker state only after reconciling
remote completion; never restore an old queue snapshot over new captures or
already completed writes. Leave quarantined raw items intact for scoped recovery.

Fresh verification (2026-10-13): Host/Guidance/Status/Controller 1196 passed and
107 subtests; API chunking/streaming/legacy parity/source authority/config guards
187 passed; Console 78 files / 532 tests passed. The original blocked operation
completed under its original ID and normal background submissions resumed.
These are bounded test suites and runtime recovery evidence, not a claim that
the entire API integration suite or every accumulated summary has passed.

本次同时修复来源包分块和失败批次阻塞调度：原文与旧操作来源保留，确认完成才
从队列移除；后续正常批次恢复处理。补写按原有配置串行推进，不改 API Key、模型
或并发。原先的 RC Tag/Release 保持不可变；当前修复通过 `release/5.1.0` 分支和
上游 PR #4 同步，不将已提交 PR 冒称已合并或新 Release 已发布。
