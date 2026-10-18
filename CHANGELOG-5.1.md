# Evolving Profile 5.1.2

> English release notes first. 中文更新说明见本文后半部分。

发布日期：2026-10-10（贡献分支准备）  
状态：release candidate; PR, merge, tag, and GitHub Release are tracked separately

## Why 5.1

EP 5.0 separated user knowledge, agent process memory, external RAG, and the
visible execution topology. EP 5.1 hardens the boundary cases that appear when
those planes meet: long sessions, incomplete provider drafts, nested host
receipts, native source review, and source-to-state coverage.

## Main changes

### 5.1.2 RC1 — cross-host preparation and agent operating guidance

- One capability registry drives8 host profiles, environment discovery, safe configuration
  previews, revision-checked apply/restore, CLI/PowerShell preparation, UI and generated matrices.
- Added a peer Host integrations configuration tab, bilingual feedback, readable/scrollable
  dialogs and explicit separation of installation candidates, EP protocol checks and native use.
- Governed new-host stdio and optional authenticated HTTP use the existing core, default read-only,
  qualified host/owner/installation identities and bounded diagnostics. Capture remains off.
- Prepared POSIX/Windows lock and path/UTF-8 handling without claiming actual Windows execution.
- Added Agent-use instructions beyond installation: routes, binding, scenario/source expansion,
  evidence accounting, failure recovery and per-host no-Hook limitations.
- Packaged static policy resources explicitly; fixed the Console launcher losing the colocated
  host script root when it enters standalone, while preserving explicit operator overrides.
- Prior local macOS feature/deployment evidence is separated from this candidate's clean-package
  results and from pending real-host/Windows acceptance. Release, contribution and merge status
  remain separately tracked; a personal pre-release is not an upstream stable release.

中文：本候选新增8类宿主准备与管理，区分识别、配置、协议、宿主接收和回答采用。
补齐跨平台基础、受控配置和只读协议；新增Agent日常使用说明，而不止安装命令。
修复打包静态依赖遗漏和Console切换工作目录后找不到配套脚本的问题。
Windows及新宿主的真实生命周期仍待实测；新版本只在本地准备，不代表远端已发布。

### Cross-date host receipt projection — 5.1.1 contribution patch, 2026-10-18

- Resolve old and archived native sessions using their authorized recorded
  path and session identity instead of the current Prompt date window.
- Read bounded tail/streamed source intervals and cache selected turn ranges,
  including running or partial turns; repeated refreshes do not reload a whole
  long transcript into memory. Unknown and budget-limited coverage remain explicit.
- Separate prepared Hook context, actual tool returns and host-received counts
  through branch and aggregate nodes. Include runtime-guidance refresh packets;
  inactive planned branches do not erase an observed subtotal.
- Preserves saved topology coordinates, memory records and retrieval policy.
  Branch publication, upstream PR acceptance and tagged releases remain separate;
  see the release ledger for actual synchronization evidence.

中文：修复长期会话跨日期后找不到原生工具回执的问题；使用经身份核对的来源路径和
有界读取，不把整份大文件反复载入内存。链路分别显示候选、Hook 准备、实际返回和
宿主接收，刷新指导返回的真实偏好包也进入统计。未知仍是未知，不补造送达或回答采用。
不改已保存的手动布局、记忆内容和召回策略；发布渠道状态见发布记录。

### Runtime guidance argument boundary — 2026-10-18

- Validate task objects before Prompt identity binding, so malformed Agent
  calls cannot raise a Python mapping AttributeError in the shared preference path.
- Reject malformed recovery events with actionable field errors; do not silently
  reinterpret runtime_events arrays or event/details into canonical evidence.
- Return invalid-argument errors for these failures and keep the stdio process
  alive for a corrected retry; do not recursively refresh on invalid guidance input.
- Explicitly acknowledge Hindsight as the development foundation in both README
  footers and NOTICE. Retrieval thresholds, source verification and stored memory
  are unchanged.

### Shared topology calibration and capability presentation — 2026-10-17

- Preserved the operator's actual Chrome-visible node calibration in one SVG
  coordinate plane, removed viewport-dependent double-scaling of label fonts,
  and replaced the English/Chinese README flow captures.
- Layout Save now writes installation-shared, revisioned settings; stale-tab
  saves and competing writes are rejected, previous settings retained, and
  corrupt/unavailable data reported rather than silently reset. Old per-origin
  browser data remains an explicit recovery draft. Text overrides are locale-specific.
- Strengthened product introductions with all five preference dimensions,
  source-linked user-memory capabilities and agent-process taxonomy, backed by
  new bilingual capability guides. No fictional benchmark or model-weight
  training claim is introduced.

中文：链路采用实际 Chrome 校准坐标和安装级共享保存，不再仅依赖网址各自的缓存；
保留旧草稿，阻止旧页面覆盖新版，字号随同一 SVG 缩放。README 展开五维偏好、
融合心智模型和用户/智能体记忆维度，图像换为分语言的真实校准界面。

### 5.1.1 — Host-specific deployment guidance — 2026-10-17

- Added English/Chinese, source-checked backend startup, configuration ownership,
  Codex and separate Claude CLI/Code-tab/Chat onboarding instructions.
- Added copyable per-host agent setup requests and explicit acceptance levels;
  protocol compatibility is not represented as verified host automation.
- Added fresh-install Controller contract/policy examples. Existing user state,
  credentials and history are not overwritten or imported by the examples.
- Advanced the product patch version and checked its release-manifest projection
  during preflight. Existing contribution branch/PR and historical RC tags remain
  separate from the current product version and a new GitHub Release.

中文：5.1.1 补全不同宿主的部署、Agent 提示词、后台启动和配置建议；
Codex、Claude Code CLI、桌面 Code 与普通 Chat 分开说明。安装构建不等于完整接入，
未实测能力不写成完成；已有 RC 标签不移动，用户私人运行配置不自动替换。

### Publication hardening and product documentation — 2026-10-17

- Rewrote English/Chinese READMEs around user value, memory-plane coordination,
  concrete workflows, actual setup commands and separately verified host readiness.
  Version changes remain in this changelog/release notes, not the README body.
- Replaced current README captures with separately localized, dated real audit
  images that exclude private Prompt lists; unknown host delivery remains unknown.
- Applied bounded dependency repairs and explicitly tested the scoped Typography
  parser override. Production-classified audit reports0; full workspace retains
  36 development/tooling package rows with0critical. See [risk disposition](docs/DEPENDENCY-RISKS.md).
- Removed author-machine path defaults from the published adapter/Guidance
  bridges, preserved explicit overrides, templated macOS worker paths and replaced
  projection fixture identities with synthetic test metadata.
- Scope parsing ignores OS account containers structurally across macOS/Linux
  home paths, instead of treating one author's login as a special word.
- Local-home leakage scanning now covers source while excluding actual Git/task
  metadata; tracked runtime/task artifacts are still rejected.
- Historical EP2.1 rollback assets are explicit opt-in integration fixtures.
  Their absence is reported as skips, not a claim of current-installer failure
  or a request to copy private backup data into this release.

### Local repair closeout — 2026-10-17

Clean-install SDK ordering, build-only startup documentation, failed-upgrade
preservation, partial-move rollback diagnostics, release source-scan boundaries
and unavailable-service UI resilience are verified as a local repair candidate.
See [repair closeout](docs/RELEASE-CLOSEOUT-5.1.md) for exact suites, source review,
real isolated startup/rollback and unmeasured limits. This entry does not mean
GitHub branches/tags/releases have received these local changes.

### Background retention hotfix — 2026-10-13

- Source-quote quality retries now receive a bounded, exact-source selector
  catalog instead of repeating the same malformed draft request. Selectors bind
  to the actual chunk hash, message role and offsets; paraphrased, stitched,
  stale or forged quotes remain rejected. The existing retry limit is unchanged.
- The runtime overview separates failed batches from child task rows using
  explicit backend lineage, and shows selected-Bank quarantine counts separately
  from the host-wide dispatcher receipt. Missing or stale evidence is not zero.
  Brief map refreshes retain a fresh published-directory state without claiming
  that unpublished semantic material has been verified.
- Scoped quarantine reconciliation requires an actual completed operation and
  an unchanged full-row snapshot. It cannot delete another Bank's records or
  release failed/in-flight work merely because unrelated requests succeeded.
- Source-linked messages now fragment within the explicit structured budget,
  so provenance envelopes larger than the normal prose target no longer make
  an otherwise valid message impossible to split. Role, original offsets,
  hashes, quote ranges and per-turn write policy remain intact; the structured
  cap still rejects oversized envelopes.
- Exhausted or policy-blocked failed operations move to persistent local
  quarantine. Raw items and original operation lineage stay available, while
  later eligible batches can proceed. Ordinary rescans cannot silently release
  quarantine. Unknown/in-flight operations retain the existing serial gate.
- Recovery retries the original remote operation after the chunking fix;
  acceptance alone never removes local raw items. Only confirmed completion
  reconciles them. Quarantined failures need scoped recovery, not a blind
  retry-counter reset.
- Regression coverage includes healthy-batch progress after a failed batch,
  quarantine persistence, source attribution, structured hard caps and
  idempotent re-chunking. Release version auditing recognizes `5.1` and `5.1.0`
  as the same product version, without equating different patches or previews.

### 1. Long-session scenario coverage

- Adds deterministic episode boundaries after a bounded number of user-message
  starts while keeping messages from the same turn together.
- Treats the boundary as a transport/coverage safeguard, not as a semantic
  claim that the user's task changed.
- Raises standard/full Session budgets without removing the compact budget or
  allowing silent truncation of exact user constraints.
- Keeps a source-linked deterministic fallback when a provider state response is
  malformed; the candidate remains pending independent coverage review.

### 2. Exact user-intent coverage

- Requires every substantive user request, constraint, correction, and answered
  request to bind to real message IDs, episode fields, and summary tiers.
- Normalizes explicit user corrections that a provider accidentally places in
  `constraints`, and recovers omitted source-visible corrections from the exact
  original user clause.
- Never derives a new correction from compressed merge-projection text.
- Resolves an omitted `answer_message_ref` only when selected assistant-report
  fields point to one unique later assistant message; multiple answers require
  an explicit model selection.

### 3. Native review provenance and host observability

- Adds a native source-coverage review receipt that is visibly distinct from
  background provider HTTP review.
- Never fabricates provider request/response hashes or an exact model identity
  for a native review whose host identity is not exposed.
- Keeps user and agent route receipts separate, including Agent Recall, Agent
  Research, returned content, source readback, and answer-use uncertainty.
- Unwraps nested MCP envelopes without copying parent aggregates into unrelated
  child nodes.

### 4. Release-grade packaging

- Adds a sanitized EP 5.1 hero illustration showing the three memory planes,
  evidence checkpoints, readback, and delivery flow.
- Adds `scripts/install-ep51.sh` with dry-run, dependency, preflight, package
  verification, and no-secret local deployment boundaries.
- Updates the release manifest, console package version, README, Notice, and
  release ledger consistently.
- Keeps JEV, external RAG, cloud backup, and provider credentials opt-in; the
  installer never enables or imports them automatically.

### 5. Host compatibility and documentation

- Documents current high compatibility with Codex, Claude Code, and Hermes
  through shared MCP/Hook, transcript-normalization, controller, and receipt
  contracts.
- Makes Codex the most deeply exercised 5.1 host and explicitly marks Claude
  Code/Hermes onboarding, native receipt, and capability-probe improvements as
  next-version work rather than claiming identical behavior today.
- Adds localized Chinese diagrams and data-rich Chinese console captures so the
  visual explanation follows the selected README language.

## Compatibility and migration

- EP 4.0/5.0 user-memory records, route aliases, L0/L1/L2 navigation, and
  existing RAG index metadata remain readable.
- Existing Embedding/Rerank indexes must still be checked against their model
  signature after a model/path/dimension change.
- Upgrade a contribution checkout by backing up Bank data, runtime settings,
  Guidance Registry, and audit receipts. Roll back by restoring the previous
  branch and configuration snapshot. Process-memory records remain separate.

## Known boundaries

- A receipt proves a call, return, delivery, or source readback state; it does
  not prove that an opaque model used a candidate in final prose.
- Long-session recovery is safe-by-default: if independent coverage cannot bind
  every user intent, the original source remains protected and no summary is
  published. This release does not convert an unresolved provider review into a
  fact.
- Native review provenance is real but its exact host/model identity can remain
  unknown; the UI says so explicitly.
- This contribution branch is not a merged/tagged GitHub Release until those
  stages are separately verified in the release ledger.

## Verification record

The release package gate records the exact command output and current counts in
[`docs/RELEASE-NOTES-5.1.0.md`](docs/RELEASE-NOTES-5.1.0.md). It includes
scenario/state/coverage tests, full Python and Console tests where available,
TypeScript/build checks, package secret scanning, and real-browser topology
evidence. Historical test counts are not reused as current results.

---

# 中文更新说明

## 为什么是 5.1

5.0 已经把用户知识、智能体过程记忆、外部 RAG 和完整执行拓扑分开。5.1
进一步处理这些平面交汇时最容易出错的边界：长会话、模型草稿不完整、嵌套
宿主回执、独立原文复核，以及用户原句到情境状态的逐条覆盖。

## 主要变化

### 2026-10-13 后台写入热修复

进一步修复原文引用质量失败后重复同样输入的问题：有界重试可以选择与实际来源
哈希、角色、位置绑定的原文片段，仍拒绝改写、拼接、过期或伪造引用，不增加重试
上限。运行概览按后端明确父子关系区分失败批次和任务行，当前记忆库的隔离队列
与整台主机的调度回执分开显示；缺失回执不显示为零。短暂地图刷新保留新鲜已发布
目录的可用状态，但不把待整理内容当作已核验摘要。隔离恢复只对真实完成、且完整
记录快照未变的原批次执行，不清空其他记忆库，不以无关成功掩盖未恢复失败。

修复原文来源包大于普通分块目标时无法分片的问题，仍遵守结构化硬预算，保留
角色、原文偏移、哈希、引用范围和每轮写入权限。失败重试耗尽或权限禁止的批次
进入持久隔离，保留原文和旧操作来源，但不再堵住后续正常批次；普通扫描不会
解除隔离。未知/处理中操作仍保持串行保护。恢复使用原操作 ID，只有确认完成
才清理队列原文，禁止通过清空队列或重置重试次数掩盖失败。

1. **长会话情境覆盖**：按安全的用户消息边界分段，同一轮消息不拆开；分段只
   是传输和覆盖保护，不擅自宣称用户开启了新任务。标准/完整摘要预算提高，
   但不允许静默截断用户的精确约束。
2. **用户意图逐条对账**：请求、条件、纠正和已答复请求必须绑定真实消息、真实
   情境字段和实际摘要层；模型误把纠正放入约束时会规范化，原始来源中漏掉的
   纠正会按原句补回；压缩合并文本不会被当作原文。
3. **独立复核来源标识**：原生 Agent 原文复核与后台 Provider HTTP 复核分开标示，
   不伪造请求哈希、响应哈希或未知的模型身份。Agent Recall、Agent Research、
   返回内容、原文回读和答案采用状态保持独立。
4. **可发布脱敏包**：新增表达三条记忆平面、证据检查点、回读和送达过程的
   5.1 配图；新增 `scripts/install-ep51.sh`，支持预检、脱敏检查、依赖安装、
   构建、试运行和不启动服务的选项。JEV、外部 RAG、云备份和 API Key 仍默认
   关闭或由操作者显式配置。

## 兼容与边界

4.0/5.0 的用户记忆、旧路由兼容映射和 RAG 索引元数据仍可读取。若模型、路径
或维度改变，索引仍需按签名检查和重建。长会话覆盖无法独立核验时，系统保留
原文并保护写入，不把不完整结果升级为事实。工具回执也不能单独证明最终回答
采用了某条候选。

## 验证

本次实际验证命令、通过数、脱敏检查、构建和浏览器证据记录在
[`docs/RELEASE-NOTES-5.1.0.md`](docs/RELEASE-NOTES-5.1.0.md)，不复用历史版本的
测试数字。
