# EP5.0 Implementation Status

EP5.0 的第一阶段已经接入现有 Host Adapter：

- `record_agent_trajectory` 记录不可变的过程证据；
- `promote_agent_process_memory` 按验证证据把轨迹提升为 Episode、Repair Pattern 或 Procedural Skill；
- `search_agent_process_memory` 按任务族、模型、版本和工具链筛选过程经验；
- `prepare_agent_process_context` 在明确调用时生成带适用条件、验证检查和来源轨迹的有界提示包；不会静默自动注入；
- `revalidate_agent_process_memory` 支持漂移状态标记和可审计恢复；跨模型经验只有 `transfer_status=verified` 才能匹配；
- `evaluate_agent_process_memory` 提供失败率、恢复时间、工具调用、Token 成本和迁移门控的确定性 A/B 评测；
- `docs/EP5.0-EVALUATION-REGISTRY.json` 固化五类任务切片、三组对照、历史只读候选策略和真实回执字段；
- `host-adapter/history_bootstrap.py` 提供按 cutoff 的 Codex/Vision JSONL 只读候选扫描；不写入 ProcessMemory、不自动晋升；
- 历史候选报告支持 `offset/limit` 分页、候选数量、工具事件覆盖和高信号统计，避免一次性加载全部历史；
- 首轮 Luna 历史分类已覆盖 278 个候选会话：文档办公 90、系统运维 61、网页/UI 47、数据/RAG 28、研究分析 17、媒体创作 7、其他 28；过程维度统计为验证 186、调试 95、工具使用 91、恢复 71、效率 39、观察 49；全部仍为 `candidate_only`。
- 全量分类报告保存为 `docs/EP5.0-HISTORICAL-AGENT-CLASSIFICATION-20260930.json`；严格 Episode 候选保存为 `docs/EP5.0-HISTORICAL-EPISODE-CANDIDATES-20260930.json`（71 条），两者均保留 `promotion_allowed=false`。
- 历史候选已导入过程库的 shadow 区：71 个 Failure Episode 候选、15 个待验证 Repair Pattern 候选；没有晋升 Procedural Skill，默认检索排除 shadow 记录。
- 历史 278 个候选已补入 `process_observation` 层，按任务族、过程维度、Session 和来源状态展示；它们是观察记录，不会默认注入。
- 15 条历史修复模式候选的 Session/JSONL 行定位已补齐并完成来源存在性复核；校准模式另有 pytest 验证证据；当前 16 条 Pattern 的 `source_recheck_status` 均为 passed。
- `Process Observation` 已写入 PRD 的稳定中间层契约，明确历史提取、验证晋升和默认检索之间的边界。
- 已用本轮实际通过的 Host Adapter 回归写入 1 条 `gpt-6.1-sol` 软件工程验证阶段能力观测；置信度保持 `unknown`，不会推导全局模型强弱；此前错误归因的 Luna 观测已标记废弃。
- 已通过 Coding Plan 官方端对 `qwen3.7-plus` 完成 5 个并行结构化任务冒烟（5/5 返回满足 diagnosis/repair/verification 契约），并写入 5 条带 `structured_output_contract_only` 范围的能力观测；这只证明本次输出契约可用，不等于跨模型技能迁移已验证。通过本机 `127.0.0.1:3211` 代理的同一请求返回 `invalid local credential`，因此不把代理路径说成已通过。
- 已将本机 EP API 的 LLM 路由改为 Coding Plan 官方 `/v1` 端点，并重启验证：API 健康、Provider `/models` 连接测试返回 200；密钥只保留在本机配置，不进入仓库、日志或界面明文。
- 同步修正了控制台的 Provider 活动档案（此前仍残留本地 3211 代理地址和本地凭据）；现在运行页、API 环境和实际 Provider 测试三者都指向官方 Coding Plan，并只以掩码显示 Key。
- 发现并修复运行配置 JSON 的结构损坏（Embedding 多余逗号、Rerank 字段缺逗号）；`json.tool`、配置接口和 Provider 页面回归均通过，页面现在显示 Coding Plan / qwen3.7-plus / 官方 `/v1`。
- 另清理了本地 RRF Reranker 上误挂的 LLM Key；Embedding/Rerank 当前均不持有 Coding Plan 凭据，只有主 Provider 使用该 Key。
- 根据架构复核，Web 端和说明已将 `skill` 的产品语义改为“可复用过程策略”：EP 默认保留动态过程观察、失败、修复模式、能力画像和情境组合；底层 `kind=skill` 仅作为兼容字段和可选 Runbook 投影，不再被描述为 EP 的核心终点。
- 本轮全面审计后确认：当前 Bank 的异步操作 `pending=0`、`completed=6982`，记忆单元约 50,780 条；API、Controller 和 Provider 均健康。后台队列中仍有 8 个 9 月 29 日测试 Bank 的遗留 pending 任务，但不属于当前用户 Bank，不阻塞日常写入。
- 新增 `config/source-of-truth.json`、`docs/EP5.0-SOURCE-OF-TRUTH.md` 和 `host-adapter/source_of_truth_audit.py`，将发布版本、运行配置、Provider、备份、用户记忆、Agent 过程记忆、原始 Session 和外部 RAG 原文分别划定唯一权威；当前现场审计全部通过。
- 已接入证据驱动的自动过程提炼：真实轨迹带独立验证回执时，自动生成 Failure Episode，并在跨任务覆盖满足条件时自动生成 Shadow Repair Pattern；不依赖人工逐条校准，仍由迁移、负迁移、漂移和 rollout 门控防止错误经验进入默认检索。
- 自动提炼边界已加固：`episode_existence_only`、`candidate_shape_only` 和 `source_locator_only` 只能证明来源定位，不能触发自动 Episode/Pattern 晋升；已将两条误聚合的历史影子模式标记为 deprecated/blocked，保留审计链但排除默认检索。
- 已执行两组独立 Python/pytest 调试校准：2 个 Failure Episode → 1 个 Repair Pattern → 1 个 Shadow Procedural Skill；当前技能只用于观察，不进入默认检索。
- 评测现在从成对真实回执计算改善率和负迁移率；缺少任务 ID、来源、独立验证器或 `real_task` 标记时不能进入 verified；
- `manage_agent_process_rollout` 提供 shadow / canary / publish / rollback 隔离；Canary 不进入普通检索，发布要求真实成对评测，撤回保留历史；
- Agent 过程图已复用星座图/图谱组件，支持星座、图谱、表格、时间线、节点详情和来源链 API 下钻；
- Console 运行状态页现在展示 Agent 过程节点、派生关系和阶段时间线，并已部署到当前 9999 运行目录；
- 过程节点支持点击查看类型、阶段、成熟度、漂移状态和摘要；运行页显示待再验证数量；
- `read_agent_process_memory` 读取单条过程记录和来源链；
- `record_agent_capability_observation` 维护任务族/阶段级能力观测，不生成全局强弱模型排名；
- `record_agent_process_draft` 仅在错误/绕路后最终成功时保存短过程草稿；普通任务不调用；
- 过程记忆单独存储在 `~/.evolving-profile/process-memory/records.json`，不写入 EP5.0 Bank 用户事实；
- Console 的运行配置增加 Agent 过程记忆模块，默认“记录、检索、注入均允许”；候选成熟度和证据门控仍决定是否实际使用。
- 历史模式现在另外生成“候选程序技能”影子记录：它们只把跨会话重复形状展示出来，不进入默认检索、不改变模型行为；只有新任务上的独立验证和迁移评测通过后才可晋升为可发布技能。这样“程序技能”页不会因安全门控而显示为空，同时不会把历史启发式分类冒充已验证能力。

生命周期保持：

```text
Trajectory → Failure Episode → Repair Pattern → Procedural Skill
```

只有独立验证器支持的 Episode 才能晋升；Pattern 需要多个已验证 Episode；Skill 需要已复现的 Pattern。过程记忆读取结果带有任务局部能力画像和干预建议，但当前 Prompt、项目约束和确定性验证结果仍然优先。

当前实现不做宿主级静默自动注入；过程经验必须由当前 Agent 显式调用 `prepare_agent_process_context` 后再决定是否采用。开启更强干预前，仍需完成真实任务轨迹采集、跨任务/跨模型迁移测试、负迁移测试和漂移回滚验收。

## 本轮验证

- Host Adapter：343 passed，35 subtests passed。
- EP5.0 专项测试：46 passed（含兼容性、项目范围、漂移、模型版本隔离、迁移状态、真实回执 A/B 评测、任务注册表、历史候选扫描与分页、Canary 回滚、提示包和证据门控回归）。
- Guidance：73 passed。
- Console Vitest：144 passed；生产构建和 standalone 构建通过。
- API 集成夹具：EP 已内置 `api/tests/fixtures/ep_templates`，Hermes 模板导入、幂等重导入和模板叠加测试 `10 passed`；不再依赖外部文档目录。
- API 全量：已加载本机 API 配置并补齐 `pg0-embedded`、`sentence-transformers`，同时将 `transformers/tokenizers` 对齐项目约束；既有全量历史套件仍包含真实 LLM 输出、并发资源和旧集成路径的失败，这些不是 EP5.0 专项测试失败。
- Console `i18n:check` 仍会报告既有页面的硬编码中文；本轮新增标签遵循现有中文默认展示路径，生产 TypeScript 构建通过。

EP5.0 PRD 契约检查覆盖：轨迹、Episode、Pattern、Skill、能力画像、干预级别、模型/环境兼容、漂移状态、版本化 Schema、EP5.0 用户记忆边界和 Console 开关均已在代码中找到对应实现或测试。
