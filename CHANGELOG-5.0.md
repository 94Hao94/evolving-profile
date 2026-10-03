# Evolving Profile 5.0.0

> English release notes first. 中文更新说明见本文后半部分。

发布日期：2026-10-02（贡献分支准备）
状态：PR preparation; not yet merged or tagged

## Why 5.0

EP 4.0 made user memory, scenario navigation, external RAG, provider fallback, and backup policy observable. EP 5.0 adds the missing execution side: the system can now preserve what an agent tried, where it failed, how it repaired the failure, how strong the evidence is, and whether a pattern is safe to reuse for another model or task.

## Main changes

### 1. Agent Process Memory

- Adds a separate process-memory plane instead of forcing agent execution lessons into user Experiences or Preferences.
- Keeps P0 Trace, P1 Event, P2 Failure Episode, P3 Repair Pattern, and P4 Skill Candidate as separate maturity layers.
- Captures planning, tool use, debugging, retrieval, verification, delivery, context management, and model adaptation dimensions without requiring one permanent task taxonomy.
- Stores task family, stage, model, tools, project/session scope, verifier quality, sample count, time window, counterexamples, and revalidation history.
- Supports per-module recording/retrieval/injection switches for trajectory, observation, failure, repair, capability, strategy, and revalidation.
- Uses an adaptive intervention ladder (`observe`, `hint`, `recommend`, `scaffold`, `guard`) rather than a permanent strong/weak model list.
- Does not promote an experience to a reusable skill from an agent's self-report alone; source events and verification remain required.

### 2. Full-chain execution topology

- Adds an execution topology with a serial spine and three parallel lanes: User Memory, Agent Process Memory, and External RAG.
- Makes forks, merges, packet assembly, writeback, audit receipt, and final response explicit.
- Adds User Preference as its own parallel route beside User Recall and User Research.
- Adds Agent Recall, Agent Research, Agent Observe, Agent Guidance, Agent Evaluation, and Agent Writeback routes.
- Uses React Flow with ELK layout and stable route IDs so the visual graph remains readable without changing the underlying receipt contract.
- Preserves node click cards, candidate lists, returned/delivered counts, source IDs, readback status, and answer-use uncertainty.

### 3. Canonical route and receipt contract

- Canonical user routes: `user_recall`, `user_research`, `user_preference`, `user_scenario_summary`, `user_source_readback`.
- Canonical agent routes: `agent_recall`, `agent_research`, `agent_guidance`, `agent_observe`, `agent_writeback`, `agent_evaluation`.
- Legacy names remain compatibility aliases and are not used as a second source of truth.
- Each node owns its own receipt projection. Parent aggregates no longer get copied into unrelated child nodes.
- The console distinguishes `observed`, `not_observed`, `unavailable`, `pending_refresh`, and `returned_zero`.
- Prompt selection shows a loading state while detail receipts are being fetched; an empty result is not shown prematurely.
- When the status API is slow, a bounded local hook-receipt fallback is exposed as a fallback source and is never mislabeled as EP Recall.

### 4. Model, RAG, JEV, and provider routing

- Keeps EP Bank retrieval and external RAG as isolated routes.
- Supports lexical search, vector search, RRF fusion, Rerank, score thresholds, index signatures, and rebuild-required detection.
- Adds model profile metadata for local and online Embedding/Rerank providers.
- Supports primary provider and fallback provider configuration without committing credentials.
- Keeps JEV optional and disabled by default. When enabled, JEV reviews evidence sufficiency, source routing, retrieval failure stage, or risk gates; it does not retrieve or write facts.

### 5. Configuration, backup, and source-of-truth controls

- Separates general overview, routing protection, runtime modules, user memory, agent process memory, retrieval/judge models, providers, RAG, scenario summaries, backups, audit logs, and LLM requests in the console.
- Adds independent Agent Process Memory module switches; disabling retrieval also disables injection without deleting records.
- Adds backup location, schedule, retention, maximum-set, minimum-success, SHA-256 manifest, and cloud-mirror verification settings.
- Establishes `config/source-of-truth.json` to document the single writable authority for release metadata, runtime configuration, guidance, backups, user memory, agent process memory, raw sessions, and external RAG.

### 6. Localization and public distribution

- English is the default UI and README language; Simplified Chinese and the existing locales remain selectable.
- Applies locale fallback to console, API/status projections, dates, receipts, node labels, and error states.
- Adds static untranslated-string checks and keeps internal route keys stable in English while exposing localized display names.
- Publishes only sanitized code, fixtures, and documentation; personal memory, prompts, runtime receipts, caches, and credentials are excluded.

## Compatibility and migration

- EP 4.0 user-memory records and L0/L1/L2 navigation remain compatible.
- Existing legacy retrieval names continue to resolve through the route registry.
- Agent Process Memory is additive; enabling it does not rewrite existing User Memory.
- Existing RAG indexes must be checked against the Embedding/index signature after a model or dimension change.
- Upgrade a contribution checkout by backing up Bank data, Guidance Registry, runtime settings, and audit receipts first. Roll back by restoring the previous branch and configuration snapshot; process-memory records are independent and can be retained or removed by policy.

## Known boundaries

- A tool receipt proves the call and delivery state, not that an opaque model used a candidate in its final answer.
- Scenario summaries and agent patterns are navigational or conditional guidance; consequential claims still require source readback.
- Capability profiles are evidence-based and time-scoped; 5.0 does not declare a permanent model ranking.
- This contribution branch is not a merged GitHub Release until the PR, tag, and release stages are separately confirmed.

## Verification record

The exact commands and current results are recorded in the release ledger after the release package gate. The gate includes release preflight, package secret scan, Python unit tests, Console tests, TypeScript/build, topology contracts, and real-browser interaction checks for loading, empty, error, fallback, click-detail, scroll, and narrow viewports.

---

# 中文更新说明

## 为什么是 5.0

4.0 主要解决了用户记忆、情景导航、外部 RAG、Provider/Fallback、备份和证据回读。5.0 增加了执行侧的完整记忆：记录 Agent 尝试了什么、哪里失败、怎样修复、验证证据有多强，以及某个过程经验是否适合迁移到其他模型、项目或任务。

## 主要更新

1. **智能体过程记忆**：独立于用户事实、经历和偏好，按 P0 轨迹、P1 事件、P2 失败事件、P3 修复模式、P4 技能候选逐层成熟；支持按任务族、阶段、模型、工具、项目和 Session 限定范围。
2. **完整链路拓扑**：用串行主干和用户记忆、智能体过程记忆、外部 RAG 三条并行路线显示分支、汇聚、上下文包、写回、审计和最终回答；用户偏好与用户召回、用户研究保持独立并行节点。
3. **统一路由与回执**：统一 User/Agent 路由键，旧工具名只做兼容；每个节点显示自己的候选、返回、送达、原文回读和答案采用状态，避免父节点数量复制到所有子节点。
4. **检索与模型配置**：EP Bank 与外部 RAG 完全分路，支持词法、向量、RRF、Rerank、索引签名和重建提示；JEV 默认关闭，只做可选的证据审查、路由和故障判断。
5. **配置与备份**：智能体过程记忆可按轨迹、观察、失败、修复、能力、策略、再验证分别开关；备份可选位置、周期、保留天数、套数、校验清单和云端镜像核验。
6. **多语言与脱敏发布**：英文默认，简体中文及已有语言可切换；内部稳定键保留英文，界面和回执支持本地化；公开包不包含个人记忆、Prompt、缓存、回执和 API Key。

## 兼容、边界和状态

4.0 的用户记忆、L0/L1/L2 和旧路由继续兼容。过程记忆是新增平面，不会自动覆盖用户记忆。工具被调用只证明调用和送达，不能单独证明最终答案采用了某条候选；情景摘要和过程模式也不能取代原文核验。本分支的 PR、合并、Tag 和 GitHub Release 会在发布记录中分开核对。
