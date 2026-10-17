# EP5.1 Global Coverage Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Use checkbox steps and preserve the progress ledger across compaction.

**Goal:** 让长会话与压缩来源可有界增量读取，建立能明确表达局部/全局审查范围的覆盖账本，保持原文、权限、预算与旧协议不变。

**Architecture:** 以固定快照、源单元及版本化覆盖回执组织工作。分段语义审稿与全局冲突审稿分离，确定性结构审计不能替代语义审查；旧v3发布路径不转换、不放宽。

**Tech Stack:** 现有Python3.11+、SQLite/文件锁/原子JSON、已配置EP Provider、现有MCP、Next/React/next-intl。v1压缩适配优先复用本地zstd可执行文件，无shell拼接；不可用时保留明确unknown，不在运行请求中自动安装依赖。

**Spec:** `docs/superpowers/specs/2026-10-16-global-coverage-ledger-design.md`（用户已于2026-10-16认可设计及计划，选择连续执行后统一独立复核；实施与验收证据见对应进度台账）。

## Global Constraints

- 不改Provider/模型/API Key/云备份配置，不发布GitHub。
- 不重置旧预算，不把局部分块accept归并成全局accept，不提升助手自述为事实。
- 禁止写入、未知范围、旧游标、过期回执和来源哈希不一致必须保留拒绝/未知。
- 旧v3摘要、用户事实/偏好、过程记忆和外部RAG保持职责分离；不批量升级旧回执。
- 单一状态与契约注册源；默认英文、简体中文完整，其余语言明确回退；不翻译原始用户内容。
- 私有源码目录不是Git仓库；不伪造Git提交。分发副本release/5.1.0已有修改必须保留，本计划不自动提交/推送。

## Review Focus

1. 压缩/改路径改变物理表示而不改语义：不得重置预算或复用未验证的旧定位（Task1/2/6）。
2. 长原句、Unicode、同turn多条消息及重叠上下文：不得丢条件或重复主覆盖（Task2/3）。
3. 各段通过但远距离纠正/项目归属未解：必须全局partial而不是accept（Task4/5）。
4. 中断、并发、权限或源变更：不得重复计账、覆盖新版本或使用旧accept（Task1/6）。
5. 摘要full未展开全部条件：界面/MCP必须明示未读，不诱导Agent将导航当全部事实（Task5/7）。

## 固定的首版默认与迁移决定

- 模式：`source_shadow`，新覆盖服务只做来源/结构账本，不自动新增模型请求、不发布新schema；旧可用路径照常运行。
- 契约注册：`config/scenario-coverage-contract.json`，包含schema版本、状态码和资源默认；Python与Console只读投影，不复制阈值到组件。
- 单个来源准备lease：最多32MiB压缩输入、64MiB解压输出、5秒墙钟；每个原始JSONL记录最多8MiB。达到任一限制必须可观察partial，不跳过无法解析的大记录，不声称支持无限单条输入。
- 单帧zstd不能假装可从任意压缩偏移续读。首版使用已有后台作业内的连续顺序解码流，按上述小lease续约并保存已验证进度；不是新增常驻服务。可选受控spool最多1GiB/活动来源、总额2GiB、同时1个解码来源；来源或权限变更立即停。进程中断无法恢复解码状态时重播已验前缀，重播也计实际资源，达到上限显式暂停；不得在每次5秒后销毁流而永远重新读相同前缀。
- 来源分段默认目标6000估算输入Token、模型输出最多2000Token、上下文重叠最多512估算Token且不计主覆盖。它们不是语义边界；实际Provider容量更低时收紧。
- 新模式模型试运行默认请求/Token额度均为0；只有显式启用模型试运行才允许正额度。建议首个受控试点每lease最多2个请求、合计16000输入+输出预留Token，继承父作业剩余额度。界面须显示这个成本选择，不偷偷启用。
- 保留旧max_attempts=3；新计账不能增加父作业次数。单位预留/实耗/未知消耗另记，禁止以切片、Provider或规范化变化刷新额度。
- 不迁移全部旧历史：仅处理新请求或显式选中的旧来源；旧v3接受状态仍按旧契约读取。受保护/空源不入模型试点。
- 每Task结束运行其相关套件；最终再运行完整后端、Console、类型检查/构建、分发包验证及真实页面点击，不把单元测试当视觉验收。

---

### Task1: 统一格式与有界原文读取

**Files:** Create `host-adapter/lib/scenario_source_codec.py`, `host-adapter/test_scenario_source_codec.py`; Modify `host-adapter/lib/session_paths.py`, `host-adapter/lib/raw_session_evidence.py`。

**Interfaces:** `locate_source(session_id, root) -> SourceLocation`；`open_source_stream(location, checkpoint, limits) -> SourceStream`；`read_source_batch(stream, checkpoint, limits) -> SourceBatch`。SourceStream仅在受控后台作业内存活，不序列化解码器；SourceLocation含路径、codec、身份状态；SourceBatch含实际SourceUnit、持久进度、已读字节与partial/原因。失败不返回伪造文本。

- [ ] 写失败测试：同一原始记录的plain/zstd产生相同raw_line_sha256/角色/Session；zstd逻辑偏移不当压缩文件seek；解码器缺失/损坏/5秒或字节上限均partial，不返回source_missing。
- [ ] 运行 `api/.venv/bin/python -m pytest host-adapter/test_scenario_source_codec.py -q`，确认缺失适配器和错误定位分别呈红。
- [ ] 实现无shell的受控zstd子进程读取，读取预算先于分配；超时终止本次子进程并保留可恢复状态。输入必须在获准根、身份核对和来源版本内；读取器不执行来源文本。
- [ ] 对暂不支持高效随机跳转的zstd，不假装常数时间seek。记录从何处重新解码及实际消耗；过大工作跨lease继续或显式暂停。缓存可选、受磁盘额度约束，源文件从不改写。
- [ ] 写单帧跨lease连续读取与中断重播测试；用元数据探针确认真实输入并不总是多独立帧。先在小临时夹具验证算法，再做真实大源的有界后台试点，不能用小文件的seek性能外推大档案。
- [ ] 运行codec+raw/archived/session_path回归；原始源/设置SHA不变。任何未支持形态仍明确unknown。

### Task2: 固定快照、来源单元与结构覆盖账本

**Files:** Create `host-adapter/lib/scenario_coverage_contract.py`, `host-adapter/lib/scenario_coverage_store.py`, `config/scenario-coverage-contract.json`, `host-adapter/test_scenario_coverage_store.py`；Modify `host-adapter/lib/scenario_source.py`只增加适配入口，不改旧默认返回。

**Interfaces:** `freeze_snapshot(location, permission, watermark) -> SourceSnapshot`；`append_source_batch(snapshot_id,batch) -> CoverageProgress`；`validate_snapshot(snapshot_id) -> ValidationResult`。Snapshot绑定选择/规范化/物理版本、顺序、水位、权限；SourceUnit区分原始定位与语义文本span。

- [ ] 写失败测试：追加不进入已冻结水位；旧记录修改、角色或权限变化拒绝；压缩/改路径不生成新语义预算；元数据排除有原始定位但混合用户请求不能被排除。
- [ ] 运行store测试见红，再实现SQLite事务、唯一键和精确版本CAS。结构记录只能来自Task1实际读取的源单元，不接受模型补ID。
- [ ] 保留`source_manifest_complete`与`semantic_review_status`两个轴；只完成结构不能输出语义已审。
- [ ] 运行store+原source/revision/retention测试；用两个并发写入者验证重复单元不重复计数，较旧快照不覆盖较新状态。

### Task3: 可解释分段与逐要求映射

**Files:** Create `host-adapter/lib/scenario_coverage_partition.py`, `host-adapter/test_scenario_coverage_partition.py`；复用`scenario_episodes.py`、`scenario_state_v3.py`的原角色/意图规则，不直接改旧v3门。

**Interfaces:** `partition_snapshot(snapshot, capacity) -> PartitionPlan`；`validate_partition(plan, snapshot) -> StructuralCoverage`；`build_requirement_catalog(partition) -> RequirementCatalog`。

- [ ] 写失败测试：所有可用源单元按顺序主覆盖一次；重叠只context_only；同turn边界不被误称新任务；中文/英文/emoji的span可精确还原；超过请求的长条件不裁剪否定。
- [ ] 红后实现基于完整条件/任务连续性及实际容量的分段；运输span不生成独立用户事实。原句目录保留source refs，不把助手建议转约束。
- [ ] 所有断点/Requirement ID绑定快照与原文span；输入缺口返回明确missing_units，禁止“凑够分段数”。
- [ ] 运行partition、旧episode、用户原句、混合角色和格式回归。未识别语义只能unknown，不硬猜项目/阶段。

### Task4: 分段语义审稿与分阶段计账

**Files:** Create `host-adapter/lib/scenario_coverage_review.py`, `host-adapter/lib/scenario_coverage_budget.py`, `host-adapter/test_scenario_coverage_review.py`, `host-adapter/test_scenario_coverage_budget.py`。

**Interfaces:** `reserve_request(job_id,stage,input_fingerprint,estimate) -> Reservation`；`settle_request(reservation,usage_or_unknown) -> Receipt`；`review_partition(partition,candidate,provider,reservation) -> LocalReview`。Provider沿用已配置主/fallback，保留真实响应指纹；API Key不进入账本/回执。

- [ ] 写失败测试：未预留不可调用；0默认额度无请求；超时用量unknown不算0；重启、改Provider、改分段或格式不重置父预算；同请求重结算拒绝。
- [ ] 红后实现分阶段预留/结算和精确原句编号选择。只对结构/复制错误沿用最多一次定向重新选择；accept=false、权限或来源变化均不“修成通过”。
- [ ] LocalReview必须列出实际读完的完整本段单元和逐意图映射、助手自述/未决状态；事实核验字段固定false，不伪装独立人工。
- [ ] 运行局部审稿、预算、现有重新选择和检查点测试；使用隔离Provider响应验证失败、中断、修改源、503，未启用模型试运行前不发真实HTTP。

### Task5: 跨段全局审查与新发布契约

**Files:** Create `host-adapter/lib/scenario_global_review.py`, `host-adapter/lib/scenario_coverage_publish.py`, `host-adapter/test_scenario_global_review.py`, `host-adapter/test_scenario_coverage_publish.py`。

**Interfaces:** `plan_global_review(snapshot,ledger) -> GlobalReviewPlan`；`review_global_partition(plan_part,source_access,provider,reservation) -> GlobalReviewPart`；`validate_global_coverage(plan,parts,ledger) -> GlobalCoverage`；`publish_segmented_navigation(snapshot,drafts,coverage,expected_generation) -> PublishedNavigation`。

- [ ] 写失败测试：各段accept但纠正/要求交界没审仍partial；远距离后续用户否定不得保留旧值为现行；同校/同cwd不合并项目；末回复只完成子任务时整体仍未决。
- [ ] 红后实现逐要求状态与有源替代/冲突关系；全局计划必须覆盖全部要求分区和所声明交界。top-k候选没有冲突不能推出全局无冲突，未覆盖边显式unknown。
- [ ] 实现`segment_coverage.v1`及新摘要schema；旧v3/full字面包含逻辑完全保留。新模式full是导航+账本链接时标明未展开要求、关键条件和回读义务，不能复用旧v3接受标签。
- [ ] 发布前重新核验快照/权限/范围/物理来源和全部必要审查；局部导航与整体接受分开，拒绝/未知不覆盖更可靠版本。外部文件/事实仍不因此已核验。
- [ ] 运行global/publish与旧v3/episode/native/整源覆盖回归；在明确的新契约范围内评价语义质量，不把结构哈希等同模型理解正确。

### Task6: 后台增量、断点与受控迁移

**Files:** Modify `host-adapter/lib/context_incremental.py`, `host-adapter/context-incremental-worker.py`, `host-adapter/lib/scenario_checkpoint.py`；Create `host-adapter/test_scenario_coverage_incremental.py`。

**Interfaces:** `process_coverage_job(job,source,config) -> JobOutcome`在新模式明确启用时运行；`invalidate_dependents(changed_units) -> DependencySet`；旧`process_summary`仍可独立调用。

- [ ] 写失败测试：默认source_shadow不新增Provider请求或发布；只选指定旧来源；尾部追加复用不变分段但重审全局修正；旧消息更改失效关联段与下游结果。
- [ ] 红后实现新账本阶段与旧作业预算/lease联动。已用attempts迁移不变，重复领取/并发/CAS/故障恢复不重结算。完成草稿、局部审稿和全局接受分别缓存，不能互相冒充。
- [ ] 集成原预算剩余额度恢复接口；protected、空源、不可读codec、未知Bank/项目、超预算均不得自动强制重排。codec可读与模型允许处理是两道不同门。
- [ ] 运行断电/lease超时/权限变化/旧基线/重试全集；新旧路径差分，确认失败证据与原文保留。

### Task7: MCP、配置与Web的同源投影

**Files:** Modify `host-adapter/evolving_profile_controller_mcp.py`, `console/src/lib/context-node.ts`, `console/src/lib/scenario-status.ts`, `console/src/components/context-memory-view.tsx`, `console/src/app/api/evolving-profile/scenario/detail/route.ts`, `console/src/app/api/evolving-profile/runtime-settings/route.ts`, `console/src/messages/*.json`；Create `console/tests/components/scenario-coverage.test.ts`。

**Interfaces:** `read_scenario_summary`新增可选`coverage_view`、`coverage_cursor`，旧调用不变；游标绑定快照/账本版本/过滤范围；新MCP结果区分summary_status/raw_source_status/source_readback和未读要求。配置从契约注册源验证，不让组件各写一套默认。

- [ ] 写失败测试：旧调用兼容；旧游标在来源改变后明确stale；full未展开条件时has_unread_requirements=true；过程ID不路由Bank read_source；不把工具返回当宿主送达。
- [ ] 由契约注册源生成/读取Python及TS状态投影；不手抄阈值。配置放现有情景摘要/覆盖审查区域：模式、来源资源、试点模型预算、成本/暂停原因；Provider仍复用原页面，不增API Key表单。
- [ ] 在现有摘要节点详情展示分段、纠正链、缺口、水位和实际用量；不新增第二张全链路图。新增字段与中英文文案、fallback一起完成。
- [ ] 运行Console全套、`npx tsc --noEmit`、`npm run build`；真实浏览器点击保存→回读→实际生效，检查加载/空/错误/恢复、长弹窗滚动、窄屏、中英文、保持用户布局。

### Task8: 真实来源对照、部署与验收

**Files:** Create `host-adapter/test_scenario_coverage_end_to_end.py`, `scripts/verify-scenario-coverage.py`；分发副本Modify `scripts/install-ep51.sh`和部署文档以增加codec预检，不在运行请求中执行全局安装。

- [ ] 先以隔离生成数据覆盖spec验收矩阵，再在临时目录重放既有14真实来源与3个长来源；原文、旧拒绝、Provider配置和用户布局哈希保持。
- [ ] 对source_shadow验证零新增模型调用；真实模型试点须使用明确配置的正额度、独立请求账本和结果范围。没有预算就停在可审的来源/结构层，不伪装语义通过。
- [ ] 独立复核全部修改，关闭Critical/Important；运行 `api/.venv/bin/python -m pytest host-adapter guidance status controller scripts/test_frozen_recall_audit.py -q`、Console测试/类型/构建，以及分发实际测试/包校验。不同测试集合不相加。
- [ ] 在安装目录备份后同步、核对生产Python树与契约哈希、验证实际后台加载及MCP调用。需要宿主重载时明确说明，不用新进程测试冒充旧进程已更新。
- [ ] 按spec逐项写验收报告：已完成/未覆盖、结构与语义状态、真实模型调用/未知成本、真实页面证据、旧路径差分、剩余风险。不把受控样本成功推成未来永不出错。

## 自检与执行交接

Spec各段分别由Task1–8覆盖；长期SourceUnit、Requirement与GlobalReview的接口名字前后一致。五项Review Focus已分别落在拥有代码的测试任务；默认shadow/0额外模型预算与旧数据不迁移避免无授权开销。当前实现细节仍由测试和代码决定，没有写入具体学校/会话ID规则。

建议执行方式：Native连续执行上述计划，独立来源读取/语义复核可以按需并行，最后一位新上下文审查员做全量复核；可避免每个任务重复启动多轮审查的额外开销。若选择逐任务子智能体，则改用subagent-driven-development的每任务审查门。

用户已确认执行方式；新契约默认source_shadow、零额外模型请求。已批准的定位和原预算恢复修补独立验收，不把它们的运行失败改写为成功。
