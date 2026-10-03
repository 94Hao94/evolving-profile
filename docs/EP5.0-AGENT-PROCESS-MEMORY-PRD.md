# EP5.0 Agent Process Memory PRD

状态：EP5.0 运行态（Agent 过程记忆与用户记忆统一版本）
目标版本：Evolving Profile 5.0
文档对象：产品、架构、数据模型、检索策略、控制台和验收方案
产品语言约束：Web 控制台默认中文；英文作为可切换语言。内部 API、数据库枚举、日志字段和跨宿主协议保留稳定英文键，页面通过本地化资源显示中文名称。

## 1. 产品判断

EP5.0 延续并统一“用户说过什么、用户偏好什么、历史事实是什么、项目情境是什么”的用户记忆能力。
但 Agent 在实际执行任务时还会产生另一类高价值信息：它在哪一步走错、为什么走错、
经过哪些尝试才修好、哪种方法有效、这种经验适用于哪个模型和工具环境。

这类信息不是用户经历，也不是普通事实。它属于 Agent 的过程经验和程序性记忆。

因此，EP5.0 增加一个与用户记忆并行的维度：

> Agent Process Memory（Agent 过程记忆）

它记录 Agent 的执行轨迹，并从经过验证的失败、修复和成功路径中提炼可复用经验，
帮助后续 Agent 少走弯路，但不把某个模型的偶然行为直接升级成所有模型都必须遵守的规则。

## 2. 研究依据与设计启发

现有研究已经形成了几条较稳定的方向：

- Reflexion 把环境反馈转成文字反思，并放入 Agent 的 episodic memory，用于下一次决策；
- Voyager 建立可复用的 skill library，把成功行动程序保存下来；
- Memp 将过程记忆拆成细粒度步骤和高层脚本，并研究 Build、Retrieve、Update；
- ReasoningBank 从成功和失败轨迹提炼可泛化推理策略；
- AgentErrorBench / AgentDebug 关注失败定位、错误类型和纠正反馈，而不是只记录最终失败；
- Experience Memory Graph 将失败轨迹与成功轨迹转换为决策图，提取可以迁移的纠错路径；
- 长期 Agent Memory 综述将 Agent Memory 概括为 write → manage → read，并特别强调错误传播、
  记忆失配、持续整合、可信反思和评测问题；
- 长期记忆管理实证研究表明，错误经验可能被相似度召回后继续传播，因此记忆添加、删除和
  轨迹评估不能只依赖“相似度高”或 Agent 自己的完成声明。

参考：

- [Reflexion](https://arxiv.org/abs/2303.11366)
- [Voyager](https://openreview.net/forum?id=P8E4Br72j3)
- [Memp: Exploring Agent Procedural Memory](https://arxiv.org/abs/2508.06433)
- [ReasoningBank](https://arxiv.org/abs/2509.25140)
- [Where LLM Agents Fail and How They Can Learn From Failures](https://arxiv.org/abs/2509.25370)
- [Experience Memory Graph](https://arxiv.org/abs/2607.13884)
- [Memory for Autonomous LLM Agents](https://arxiv.org/abs/2603.07670)
- [How Memory Management Impacts LLM Agents](https://aclanthology.org/2026.acl-long.27.pdf)
- [Managing Procedural Memory in LLM Agents: Control, Adaptation, and Evaluation](https://arxiv.org/abs/2606.23127)
- [Governing Evolving Memory in LLM Agents](https://arxiv.org/abs/2603.11768)

近期研究对本 PRD 的直接提醒是：过程技能的跨任务、跨角色和跨模型迁移并不均匀，必须
单独测量迁移轴；长期记忆需要把选择性遗忘、持续整合、因果检索和漂移治理作为独立能力，
不能只用“召回命中率”或时间衰减代表成长质量。

## 3. 目标与非目标

### 3.1 目标

1. 完整保存 Agent 任务执行的可验证过程，而不是只保留最终答案。
2. 能定位“失败发生在哪里、根因是什么、如何修复、修复是否验证通过”。
3. 从多次轨迹中提炼跨任务可复用的 Repair Pattern 和 Procedural Skill。
4. 根据当前模型、Agent 角色、工具链、项目和任务类型选择适用经验。
5. 支持不同 Agent 之间共享经过验证的经验，同时防止模型能力差异造成误导。
6. 将 Agent 过程记忆与 Project、Session、Facts、Experiences、Entities、Preferences 连接起来。
7. 提供星座图、图谱、时间线、失败链路和技能详情的统一可视化。
8. 通过可重复的 A/B 测试验证经验是否减少失败、时间和无效工具调用。

### 3.2 非目标

- 不把每一次工具调用都直接写成长期记忆。
- 不把 Agent 的自我评价直接当成事实。
- 不把一次失败自动升级成全局规则。
- 不把某个模型的局部技巧强行注入所有模型。
- 不改变既有用户事实、偏好和 Scenario Summary 语义。
- 不默认把完整轨迹注入下一次上下文。
- 不通过记忆系统替代编译器、测试框架、渲染器或其他确定性验证器。

## 4. 总体架构

```text
用户记忆维度
  Facts / Experiences / Entities / Preferences / Scenario Summary

Agent 过程记忆维度
  Raw Trajectory
      ↓
  Failure Episode
      ↓
  Repair Pattern
      ↓
  Procedural Skill / Runbook

共享关系图
  User / Agent / Model / Tool / Project / Session / Task / Source / Evidence
```

用户记忆回答“用户、项目和世界发生了什么”；Agent 过程记忆回答“Agent 如何完成任务、
哪里失败、什么方法被验证有效”。二者通过同一个 Evidence Graph 关联，但不混成一个扁平
的文本池。

### 4.1 与 EP5.0 用户记忆平面的关系

```text
EP5.0 User Memory Plane
  → 用户事实、经历、实体、偏好、情境和外部资料

EP5.0
  → Agent 轨迹、失败、修复、程序技能和模型适用范围

两者共享
  → Project、Session、Task、Source、Tool、Model 和验证证据
```

Agent 可以是 Experiences 中的主体，但 Agent Process Memory 不能被 Experiences 取代。
Experiences 保留事件真实性和时间顺序；Process Memory 负责从事件中提炼可执行经验。

### 4.2 初始记忆平面

为了防止 EP5.0 与已有对象互相覆盖，运行时先采用以下五个语义平面。这里的“五个”是
当前实现的初始分区，不是永久固定的产品枚举。未来如果出现新的存储责任（例如模型原生
状态、评估数据集或多 Agent 协议状态），应通过版本化的平面注册表增加或拆分平面，而
不能把新内容硬塞进语义不匹配的旧平面。

```text
User Knowledge Plane
  Facts / Experiences / Entities / Preferences / Scenario Summary

Agent Process Plane
  Trajectory / Failure / Repair / Skill / Model Compatibility

Task Working Plane
  当前 Task Contract、临时假设、待核验字段和本轮工具状态

External Evidence Plane
  外部 RAG、文件、网页和用户指定资料

Audit Plane
  Tool Receipt、Verifier Result、Prompt Binding、Delivery 和 Provenance
```

每个平面有自己的写入和读取规则：

- User Knowledge Plane 可以影响任务理解，但不能被 Agent 过程判断自动改写；
- Agent Process Plane 可以提供行动建议，但不能覆盖用户当前要求；
- Task Working Plane 可以暂存未决假设，但不能自动升级成长期记忆；
- External Evidence Plane 只代表外部资料，不能直接变成 EP 事实；
- Audit Plane 只记录证据和回执，不作为行动建议本身。

任何记忆跨平面移动都必须经过明确的 `promotion` 事件，并保留来源、理由、版本和验证状态。
平面注册表还应记录 `plane_version`、读写权限、保留期限和导出策略，使新增平面不会改变
既有对象的含义，也不会让旧记录失去可读性。

### 4.3 记忆对象的单向派生规则

EP5.0 保留用户记忆平面的单向证据原则，并扩展到 Agent 过程：

```text
原始来源 / 用户原话 / 工具回执 / 验证结果
  ↓
Facts / Experiences / Raw Trajectory / Failure Event
  ↓
Observations / Failure Episode / Task Context
  ↓
Preferences / Repair Pattern / Scenario Summary
  ↓
Mental Models / Procedural Skill
```

上层对象可以帮助检索和解释，但不能反向证明下层对象。Skill 不能证明事实，Preference
不能证明用户说过什么，Scenario Summary 不能证明金额和版本，Repair Pattern 不能证明
当前环境仍然相同。

P0–P4 是当前的成熟度导航，不是所有记录都必须逐层经过的固定流水线。某些任务可以只
保留 P0/P1 审计证据，某些经过外部验证的模式可以直接关联到 P3；若未来需要插入新的
中间层，使用版本化 `kind` 和 `maturity` 映射，不改变旧记录的解释。

## 5. Agent 过程记忆的四类记录

历史回填和实时采集之间增加一个中间层 `Process Observation`。它记录任务片段、过程维度、
阶段、工具、Session/Project/Task 归属和来源定位，成熟度为 `observed`，默认不参与检索。
它让“历史已提取”与“已经验证可以复用”分开，避免大量客观轨迹因为尚未晋升 Skill 而在界面上
显示为空。Process Observation 只能经过来源回读、独立验证和重复复现后，才向 Episode、Pattern
或 Skill 派生。

### 5.1 Raw Trajectory：原始执行轨迹

这是不可变的过程证据，记录：

- task、project、session 和 prompt 标识；
- Agent 角色、模型和模型版本；
- 工具调用顺序及参数摘要；
- 工具返回状态、退出码和错误类型；
- 文件、代码、页面或文档的变化；
- 测试、编译、渲染、视觉检查或用户反馈结果；
- 每个关键动作和结果的责任主体（Agent、用户、工具、评估器或外部系统），避免把工具或
  用户修复的结果错误归因给 Agent；
- 开始时间、结束时间、耗时、Token 和重试次数。

Raw Trajectory 默认进入冷存储或审计层，不直接注入上下文。

### 5.2 Failure Episode：失败事件

Failure Episode 是一段已经定位的失败过程，不只是“任务失败”。它应说明：

- 触发条件；
- 失败阶段；
- 失败类型；
- 直接症状；
- 根因假设；
- 支持根因的证据；
- 尝试过但无效的路径；
- 最终修复路径；
- 修复后的验证结果；
- 仍未确认的部分。

失败类型可以包括：

```text
planning_error       计划或任务拆解错误
scope_error          项目、Session 或文件范围选错
tool_error           工具选择、参数或调用顺序错误
format_error         文档、代码或结构格式错误
verification_error   没有正确验证或误判完成
retrieval_error      Recall、Research 或 RAG 路径错误
context_error        上下文缺失、过量或混入无关内容
model_limit          当前模型能力或上下文限制
environment_error    权限、依赖、服务或运行环境问题
```

### 5.3 Repair Pattern：修复模式

Repair Pattern 是从 Failure Episode 中提炼出的“在什么条件下采取什么修复动作”。
它不是完整轨迹，而是带前提、动作和验证器的局部策略：

```text
问题条件 → 诊断信号 → 修复动作 → 验证方法 → 适用范围
```

例如：

```text
条件：前端按钮无响应，后端接口正常
诊断：DOM 中存在按钮但没有事件回执
修复：检查组件状态绑定和事件处理器，不先修改后端 API
验证：浏览器点击 + 页面状态变化 + Console 无错误
适用：React/Next.js 交互问题
```

### 5.4 Procedural Skill / Runbook：程序技能

Procedural Skill 是经过多次验证、可以在类似任务中主动参考的高层流程。它比 Repair
Pattern 更抽象，可能包含多个步骤和分支。

```text
正式 PPT 交付流程
  → 先做结构检查
  → 批量检查字体、页数、溢出和表格
  → 只对异常页做重点渲染
  → 对封面、目录、核心图表和结尾页做视觉核对
  → 最后验证文件可打开、页码和导出结果
```

Skill 必须保留适用条件和失败边界，不能变成无条件执行脚本。

## 6. Agent 维度与星座图

5.0 的 Agent 过程记忆可以增加一组专属维度，但这些维度表示“过程属性”，不复制用户
偏好的五个维度。

建议的 Agent 过程维度是：

| 维度 | 含义 | 典型节点 |
|---|---|---|
| Planning | 任务理解、拆解和路线选择 | 目标遗漏、范围错误、无效计划 |
| Tool Use | 工具选择、参数、顺序和重试 | 错用工具、参数错误、重复调用 |
| Debugging | 故障定位、根因判断和修复 | 根因、修复动作、失败尝试 |
| Verification | 测试、编译、渲染、视觉和用户验收 | 验证器、通过/失败、误判完成 |
| Delivery | 文件、格式、交付和外部结果 | 排版、导出、发送、可打开性 |
| Retrieval | Recall、Research、RAG 和来源核验 | 漏召回、误召回、范围混淆 |
| Context Management | 上下文压缩、摘要、Token 和记忆选择 | 过量注入、缺少关键前文 |
| Model Adaptation | 模型、版本、工具能力和迁移 | 某模型有效、另一模型失效 |

星座图只增加节点和连线的语义维度，不改变用户事实、经历、偏好和情境摘要的布局。
可视化视图建议包括：

- Agent 过程星座图：Agent、模型、工具、失败、修复、技能；
- Failure → Repair 图谱：失败节点到根因和修复动作；
- Model Applicability 图谱：经验与模型、版本、工具链的适用关系；
- Task Timeline：任务阶段、工具调用、失败、修复和验证；
- Skill Evolution：同一技能的版本、成功率、失效条件和替代方案。

Agent 星座图与现有 Facts/Experiences/Preference/Scenario 图使用统一节点、连线、透明度、
点击详情和时间线交互，但颜色语义不同：

```text
蓝色：Agent / Model
紫色：Task / Project / Session
红色：Failure / Conflict
绿色：Verified Repair / Successful Skill
橙色：Tool / Verifier
灰色：Unknown / Deprecated
```

### 6.1 中文优先与多语言

Agent 过程记忆的内部键使用稳定英文，便于 MCP、数据库、跨宿主和版本迁移：

```text
planning / tool_use / debugging / verification / delivery
retrieval / context_management / model_adaptation
```

Web 端默认显示中文：

| 内部键 | 默认中文显示 |
|---|---|
| Planning | 规划与拆解 |
| Tool Use | 工具使用 |
| Debugging | 调试与修复 |
| Verification | 测试与验收 |
| Delivery | 交付与发布 |
| Retrieval | 检索与证据 |
| Context Management | 上下文管理 |
| Model Adaptation | 模型适配 |
| Failure Episode | 失败事件 |
| Repair Pattern | 修复模式 |
| Procedural Skill | 程序技能 |
| Raw Trajectory | 原始轨迹 |
| Observed | 已观察 |
| Diagnosed | 已诊断 |
| Repaired | 已修复 |
| Verified | 已验证 |
| Replicated | 已复现 |
| Generalized | 已泛化 |
| Deprecated | 已弃用 |

任务族、执行阶段、结果状态、成熟度、冲突类型和星座图图例都遵循同一规则：接口使用
英文键，Web 默认中文，用户可以在语言菜单切换英文。后端返回未知枚举时，页面显示中文
兜底文本和原始键，不能出现空白标签或直接把内部键当成面向用户的完整说明。

中文内容验收包括：

- 默认中文页面不能出现未翻译的关键标题、按钮、状态或错误提示；
- 中英文切换不能改变数据、排序、图谱节点 ID 或查询结果；
- 中文较长的任务族和状态名称不能挤压节点、按钮或表格列；
- 图谱详情同时显示中文名称和必要的英文键，便于排查回执；
- Agent 过程记忆正文保留来源原文语言，页面标签和系统生成说明按当前语言显示。

### 6.2 维度设计原则：固定骨架，动态标签

5.0 不能把所有任务都硬塞进一套互斥分类。不同任务需要共享一套稳定骨架，同时允许
任务域、工具链和失败方式不断扩展。因此 Agent 过程记忆采用三种信息：

```text
核心维度：稳定、少量、用于检索和图谱分层
任务标签：可扩展、描述任务类型和产物类型
关系属性：描述模型、环境、项目、Session 和证据条件
```

核心维度回答“这段经验属于哪种过程能力”；标签回答“它发生在哪类任务”；关系属性
回答“它在什么模型、工具、项目和阶段下成立”。这三者不混为一个 `type` 字段。

### 6.3 任务类型维度

为了覆盖实际使用中的五花八门任务，系统需要一个可扩展的 Task Archetype 层。第一版
建议包含以下任务族：

| 任务族 | 典型工作 | 主要过程风险 |
|---|---|---|
| Software Engineering | 编程、重构、接口、测试、部署 | 需求误解、范围错误、回归遗漏、依赖冲突 |
| Document / Office | Word、PDF、Excel、PPT、正式材料 | 结构错误、格式破坏、数据错配、视觉漏检 |
| Research / Analysis | 资料研究、比较、采购、政策和方案分析 | 来源错配、时间线混淆、证据不足、过度推断 |
| Web / UI Operation | 浏览器、桌面应用、表单和网页交互 | 选错页面、状态未确认、点击无效、权限阻塞 |
| Data / RAG | 数据清洗、导入、索引、检索和知识库 | Schema 不兼容、召回误差、索引过期、污染 |
| System / DevOps | 服务、端口、配置、备份、恢复和监控 | 环境漂移、权限、启动顺序、回滚失败 |
| Media / Creative | 图片、视频、音频、渲染和素材处理 | 素材错配、渲染成本、质量验收、版权边界 |
| Communication / Delivery | 致辞、邮件、汇报、对外交付 | 身份越界、语气失配、事实夸大、格式不合 |
| Learning / Explanation | 教学、复习、术语解释、因果推演 | 解释层级不合、例子错误、概念混淆 |
| Coordination / Multi-agent | 委派、并行、交接和结果合并 | 状态丢失、重复劳动、责任不清、回执缺失 |
| Health / Personal Decision | 个人决策、健康和日常安排 | 证据等级、时效、风险和授权边界 |

任务族不是永久封闭枚举。新任务先进入 `other` 或多个标签组合，经过多次轨迹后再
决定是否形成新的稳定任务族，避免为单个项目过拟合出一套分类。

### 6.4 执行阶段维度

同一种失败在不同阶段含义不同。所有过程记忆都应带有一个阶段序列：

```text
understand       理解需求、范围和约束
plan             拆解目标、选择路线和工具
retrieve         查找历史、资料、偏好或外部 RAG
act              编码、编辑、调用工具或生成内容
observe          读取返回、页面、文件或环境状态
verify           测试、编译、渲染、比较、用户验收
recover          诊断、修复、重试、回滚或换路
deliver          导出、发送、发布或交付
reflect          总结可复用经验和失效条件
```

这样可以区分“计划本身错误”和“计划正确但验证漏掉了问题”，也能让 Agent 在执行中
只读取当前阶段相关的过程记忆。

### 6.5 结果与质量维度

仅记录成功/失败不够。过程记忆还要描述结果性质：

```text
correct           结果经确定性验证或权威来源支持
partially_correct 部分目标完成，仍有明确缺口
recovered         先失败，后通过修复完成
regressed         修复后引入新的问题
blocked           权限、服务、输入或环境导致无法继续
ambiguous         结果看似完成，但缺少足够证据
inefficient       结果正确，但路径明显绕路或成本过高
not_applicable    经验在当前环境或模型上不适用
```

`inefficient` 不能自动等于 `failed`。例如一个 PPT 最终正确，但执行时间过长，应该
形成效率类经验；一个程序测试通过但结构严重恶化，则应记录质量退化。

### 6.6 证据成熟度层级

Agent 过程记忆必须有独立的成熟度，不和事实的 `valid/invalid` 混用：

```text
observed          轨迹中观察到，但尚未解释
diagnosed         已提出根因并有初步证据
repaired          修复动作已执行
verified          通过测试、渲染、工具回执或用户验收
replicated        在相似任务中再次验证
generalized       已在明确声明的任务、环境或模型范围内确认具有迁移价值
deprecated        环境、模型或工具变化后不再推荐
```

只有 `verified` 及以上的 Repair Pattern 才能进入普通主动检索；跨项目或跨模型共享还
必须具备相应的迁移验证，`generalized` 只表示已验证的声明范围，不表示对所有 Agent
全局生效。声明范围还必须记录正例、反例、样本覆盖和未知边界；范围之外仍按
`candidate` 或 `unknown` 处理。`observed` 和 `diagnosed` 只在故障排查或明确研究时读取。

### 6.7 Agent 记忆的五层结构

为了与 EP5.0 的用户记忆配合，Agent 过程记忆采用从原始到抽象的五层，而不是把所有
内容都放在同一张向量表：

```text
P0 Trace        原始轨迹和工具证据，只读审计
P1 Event        单个错误、动作、验证和状态变化
P2 Episode      一次任务中的失败、恢复或高成本过程
P3 Pattern      跨 Episode 的根因和修复模式
P4 Skill        经过多次验证的程序技能或 Runbook
```

读取原则是从高层向下定位，从低层向下核验：先读 P4/P3 预防和行动提示；如果仍有
争议，再读 P2；需要原始证据时回到 P1/P0。P4 不能替代 P0，任何高层技能都必须能
回指底层轨迹和验证结果。

### 6.8 Task Contract：所有过程记忆的共同入口

无论是写代码、改 PPT、查资料还是操作网页，执行前都先形成一个轻量的 Task Contract，
用于让不同任务进入同一套路由机制：

```text
task_id
task_archetype          任务族
objective               目标
deliverable             交付物
constraints             明确限制
primary_context         Project / Session
agent_role              Agent 角色
model_profile           模型和推理档案
toolchain               可用工具链
verification_plan       计划使用的验证器
unresolved_slots        尚未明确的关键字段
```

Task Contract 不是新的长期记忆，而是当前执行的工作投影。它连接 Preference、Scenario
Summary 和 Agent Process Memory，使检索可以围绕完整任务匹配，而不是只按最后一句话
或一个泛化关键词找经验。

任务族识别采用“规则初筛 + Agent 判断 + 结果回写”。规则可以识别明显的代码、文档、
研究、网页和系统任务；Agent 可以在多个候选之间选择或保留混合任务；任务结束后再用
实际轨迹评估路由是否正确。系统不能因为一个关键词就永久改变任务族。

核心过程维度采用多标签，而不是互斥分类。例如网页按钮故障可以同时标为
`Tool Use + Debugging + Verification`；正式 PPT 导出问题可以是
`Document/Office + Delivery + Verification`。任务族描述工作对象，过程维度描述能力环节，
阶段描述时间位置，结果状态描述结果，成熟度描述证据强度。一个记录不得把这些轴压成
单个标签。

## 7. 关系模型：Agent 记忆如何与用户记忆结合

同一条过程记忆可能属于多个 Session 或 Project，因此不能只保存一个上下文 ID。
建议关系模型支持：

```text
AgentTrajectory
  ├─ primary_session
  ├─ related_sessions[]
  ├─ primary_project
  ├─ related_projects[]
  ├─ task
  ├─ agent
  ├─ model
  └─ toolchain
```

与现有对象的连接包括：

```text
Agent Failure Episode
  → 产生于某个 Session / Project
  → 针对某个 Task
  → 使用某个 Agent / Model / Tool
  → 影响某个 Fact / Experience / Entity / Document
  → 通过某个 Verifier 得到结果
  → 提炼为 Repair Pattern 或 Skill
```

例子：

```text
同一 PPT 项目
  → 用户事实：交付对象、学校、正式用途
  → 用户偏好：正式材料需要视觉检查
  → Agent 经历：多次修改并反复渲染
  → Agent Failure Episode：逐页全量渲染导致流程过慢
  → Repair Pattern：结构检查优先，异常页重点渲染
  → Skill：正式 PPT 高效验收流程
```

这样用户偏好告诉 Agent“交付标准是什么”，Agent 过程记忆告诉 Agent“如何更快达到
这个标准”，Project/Session 则说明“这条经验发生在什么环境”。

### 7.1 关系类型和方向

关系图必须区分关系语义，不能只画一条无类型的线。建议至少支持：

```text
performed_by        轨迹由哪个 Agent 执行
used_model          轨迹使用哪个模型或版本
used_tool           轨迹调用了哪个工具
occurred_in         轨迹发生在哪个 Session / Project
targets             任务针对哪个文件、系统、实体或文档
failed_at           失败发生在哪个阶段或动作
caused_by           失败的候选根因
repaired_by         采用了哪个修复动作
verified_by         哪个测试、渲染器、工具回执或用户验收支持结果
derived_from        Pattern / Skill 来源于哪些 Episode
applies_to          经验适用于哪些任务、模型和工具链
contradicts         与哪个经验或规则冲突
supersedes          替代哪个旧版本
influences          对用户偏好、项目选择或流程有何影响
```

关系方向也有明确边界：

```text
用户事实/偏好 → 约束任务目标和交付标准
Project/Session → 提供任务情境
Agent Trajectory → 记录实际执行
Verifier → 证明结果或发现失败
Failure Episode → 产生 Repair Pattern
Repair Pattern → 在条件匹配时建议行动
```

Agent 过程记忆可以被用户偏好和情境解释，但不能反向改写用户事实；除非用户明确确认，
Agent 的过程判断也不能自动变成用户偏好。

### 7.2 归属和共享规则

一条过程记忆可以关联多个 Session 和 Project，但应区分：

- `primary_context`：主要发生环境；
- `secondary_contexts`：被引用、复用或验证的其他环境；
- `transfer_scope`：允许迁移到哪些任务和模型；
- `visibility_scope`：哪些宿主、Agent 和用户可以读取。

同一 Project 下的多个 Session 不自动共享全部失败经验。只有关系边、任务类型和权限
都允许时，才将 Pattern 或 Skill 暴露给另一个 Session。

## 8. 写入、提炼和晋升流程

```text
执行开始
  → 捕获轨迹
  → 任务结束或阶段结束
  → 确定性验证器收集结果
  → 失败定位 / 成功模式识别
  → Failure Episode 候选
  → Repair Pattern 候选
  → 适用范围和冲突审查
  → 发布为 Agent Process Memory
```

### 8.1 按任务族选择提炼重点

不同任务需要不同的提炼维度。系统先识别任务族，再选择提炼模板；模板只决定需要
观察哪些字段，不决定最终结论。

| 任务族 | 优先提炼 | 必须保留的证据 |
|---|---|---|
| Software Engineering | 需求理解、设计决策、错误签名、测试和回归 | diff、测试输出、编译结果、环境版本 |
| Document / Office | 内容结构、格式策略、渲染流程、视觉缺陷和导出 | 原文件、渲染图、页数/字体检查、最终文件 |
| Research / Analysis | 查询路线、来源质量、冲突裁决、停止条件 | URL/文档、引用、时间和冲突记录 |
| Web / UI Operation | 页面范围、控件定位、状态变化、失败重试 | 截图、DOM/AX 状态、浏览器日志、操作回执 |
| Data / RAG | 数据契约、索引版本、召回组合、重排和来源 | schema、index signature、候选和 readback |
| System / DevOps | 依赖、启动顺序、配置、健康检查、回滚 | 命令输出、服务状态、配置 diff、恢复结果 |
| Media / Creative | 素材、参数、渲染链、质量和交付格式 | 输入素材、渲染结果、媒体元数据、验收记录 |
| Communication / Delivery | 身份边界、语气、受众、事实和格式 | 用户要求、来源材料、最终交付物 |
| Learning / Explanation | 用户已有水平、概念链、例子效果和误解点 | 用户追问、纠错、迁移测试结果 |
| Coordination / Multi-agent | 委派边界、交接状态、重复工作和完成回执 | task state、handoff、结果回执、去重键 |

同一轨迹可以同时属于多个任务族，但应保留一个主任务族和受预算约束的次级标签，防止
图谱无限膨胀。次级标签的数量不是业务语义常量，应由页面性能、任务复杂度和检索预算
共同决定；超出预算时保留聚合标签和可下钻的完整关系。

### 8.2 提炼产物的分离

一次任务结束后，不直接生成一条“大而全”的总结，而是并行生成几个小产物：

```text
Outcome Record     最终结果和是否完成
Failure Record     失败和症状
Cause Hypothesis   根因及证据状态
Repair Record      修复动作和验证结果
Efficiency Record  耗时、重复、绕路和资源成本
Transfer Note      能否迁移到其他任务/模型
```

这些产物可以关联在同一 Episode 下，但检索时按缺口读取。例如用户只问“如何避免
再次出现这个错误”，读取 Repair Record；用户问“为什么这次这么慢”，读取
Efficiency Record；用户问“这个方法适不适合另一个模型”，读取 Transfer Note。

### 8.2.1 条件式过程草稿

EP5.0 不要求 Agent 在每个任务结束后都写总结。只有同时出现明显绕路、错误、回退、重复
尝试或验证失败，并且随后出现验证通过、用户确认或确定性交付成功时，Agent 才可以主动
提交一段短的 `Process Brief` 草稿。草稿只写入 Agent Process Plane 的候选缓存，包含：

```text
触发问题 → 失败/绕路 → 最终修复 → 验证证据 → 适用条件 → 不能套用的边界
```

草稿建议控制在几百字以内，由当前 Agent 直接从已知过程证据生成；如果 Agent 没有生成，
系统保留原始轨迹即可，不启动额外模型调用追问。草稿不能证明事实，不能直接晋升 Skill，
也不能因为写入成功就进入默认检索。只有独立验证器和重复复现满足晋升门槛后，才转为
Failure Episode、Repair Pattern 或 Procedural Skill。

### 8.3 什么情况下写入

- 发生了明确错误并且有工具或测试证据；
- 同一错误经过修复后通过验证；
- 任务完成但过程出现明显绕路、重复或高成本；
- 用户指出 Agent 的方法有问题并给出纠正；
- 多个任务中出现同一种失败或成功策略。

### 8.4 什么情况下不晋升

- 只有 Agent 自己说“完成了”；
- 只有一次偶然失败，没有根因证据；
- 经验只适用于一个文件、一个版本或一次临时环境；
- 修复没有被测试、渲染或用户验收；
- 经验与已有 Skill 冲突但没有裁决；
- 内容可能来自错误的历史记忆或错误的外部资料。

未达到晋升条件的内容保留在候选区，不进入默认检索。

## 9. 读取和注入策略

Agent Process Memory 不应每轮自动加载。建议分三个触发位置：

### 9.1 任务开始前

当任务类型、工具链、模型和项目与已知失败模式相似时，读取少量高置信的预防经验。
这类内容只给“注意事项和建议路线”，不能把具体操作强行当作命令。

### 9.2 执行中出现错误

当工具返回错误、测试失败、渲染失败或连续重复操作时，按错误签名、当前阶段和工具
查找对应 Failure Episode 与 Repair Pattern。这是最应该主动读取的阶段。

### 9.3 任务结束后

通过确定性结果和用户反馈更新成功率、适用范围和失效时间。只有完成验证的经验才能
进入更高层的 Procedural Skill。
若本轮满足条件式过程草稿的触发条件，Agent 可以在 Stop 前调用
`record_agent_process_draft`；该调用只保存短草稿和来源轨迹 ID，不重新发送完整对话，
也不依赖 Coding Plan 缓存。

读取预算建议：

```text
预防提醒：从低预算开始，按任务复杂度和上下文余量自适应扩展
故障修复：优先 1 条主修复和 1 条替代路径，信息不足时再增量读取
复杂流程：按阶段组织，数量受任务预算和相关性门控限制
完整轨迹：只用于审计或明确要求，不默认注入
```

### 9.4 路由决策矩阵

读取 Agent 过程记忆时，路由由“任务族 + 当前阶段 + 错误信号 + 适用范围”共同决定：

| 当前情况 | 首选读取 | 读取内容 |
|---|---|---|
| 新任务开始，目标和工具链明确 | P4 Skill / P3 Pattern | 预防性步骤和已知限制 |
| 计划阶段出现范围或目标不确定 | P2 Episode / Planning Pattern | 常见拆解错误和范围核对方法 |
| 工具调用失败 | Failure Episode / Tool Pattern | 错误签名、参数和替代工具 |
| 编译、测试或渲染失败 | Debugging Pattern / Repair Record | 根因假设和修复顺序 |
| 连续重复相同动作 | Efficiency Record / Context Pattern | 如何停止绕路、缩小范围或换路线 |
| 最终交付前 | Verification / Delivery Skill | 检查清单和最低验收标准 |
| 模型或宿主切换 | Model Adaptation / Transfer Note | 旧经验是否可迁移、需要哪些重新验证 |
| 用户明确询问“之前怎么修的” | P2/P1 有界回放 | 具体 Episode 和来源证据 |

### 9.5 过程记忆与 EP5.0 路由协同

```text
User Prompt
  ↓
Get Preference：读取用户的目标、表达和交付偏好
  ↓
按证据缺口选择 Scenario Summary、Agent Process Memory、Recall / Research 或 RAG
  ↓
Agent 执行与验证
  ↓
  Trajectory / Failure / Repair 写入候选区
```

上图是可组合的路由骨架，不是每轮必须执行的固定顺序。纯自足任务可以跳过历史路线；
需要范围定位时先读 Scenario Summary；需要历史事实时走 Recall/Research；需要外部资料时
走隔离的 RAG；需要规避已知执行坑时才读取 Agent Process Memory。各路由的候选必须在
进入上下文前经过来源、范围和适用条件检查，不能因为某一路由命中就自动触发所有其他路由。

过程记忆的读取通过显式的 `prepare_agent_process_context` 形成有界 `Memory Hint Packet`：
只返回通过默认成熟度门控的候选、适用条件、避免条件、验证检查、来源轨迹和任务局部干预等级。
工具回执必须标记 `automatic_injection=false`，由当前 Agent 决定是否采用；宿主不得因为模块已启用
就把候选静默拼入上下文。关闭注入开关或候选为空时，EP5.0 原有 Recall、Research、Preference 和
RAG 路由保持不变。

不同模块的职责必须保持清楚：

- Preference 决定“用户希望怎样完成和交付”；
- Scenario 决定“当前任务处在什么环境”；
- Facts / Experiences 提供“历史上发生了什么”；
- Agent Process Memory 提供“Agent 以前怎样做、哪里会失败”；
- RAG 提供“外部资料写了什么”；
- Verifier 提供“这次结果是否真的通过”。

### 9.6 防止过程记忆压过当前任务

Agent Process Memory 只能作为行动前参考或故障后的候选修复路线，不能直接覆盖：

- 当前用户的新要求；
- 当前项目的明确约束；
- 当前文件、工具和环境的真实状态；
- 新的测试、编译、渲染或用户验收结果。

如果新证据与旧过程经验冲突，旧经验降为历史参考并进入重新验证队列。

## 10. 模型适用范围与迁移

每条 Repair Pattern 和 Skill 都要标记：

- `model_family`；
- `model_version`；
- `agent_role`；
- `host`；
- `toolchain`；
- `task_type`；
- `domain`；
- `capability_requirements`；
- `success_count` / `failure_count`；
- `last_verified_at`；
- `supersedes` / `counterevidence`。

为适配未来模型、工具协议和多模态环境，还应保留：

- `model_capability_fingerprint`：可观测能力和工具调用特征的版本化摘要，不等同于模型名称；
- `environment_fingerprint`：宿主、依赖、权限、工具协议和验证器版本；
- `modality_profile`：文本、图像、音频、视频或结构化状态等输入输出能力；
- `evaluation_set_version`：能力观测来自哪一版校准集和哪类任务分布；
- `selection_exposure`：经验被展示、采用和跳过的次数，用于避免只保留成功样本。
- `drift_status`：事实语义或程序流程是否出现漂移，以及触发了哪类再验证。

另外增加一个独立的 `compatibility_profile`，用于描述经验与模型和环境的关系：

```json
{
  "model_family": "gpt-6-sol",
  "model_version": "observed-version",
  "agent_role": "coding-agent",
  "host": "codex",
  "toolchain": ["typescript", "playwright"],
  "capabilities_required": ["browser-control", "test-runner"],
  "transfer_status": "verified|candidate|unknown|blocked",
  "revalidation_due": "2026-10-01"
}
```

模型名称只是一个条件，不能单独决定是否读取。真正的适用性还要看任务族、工具链、
环境、验证器和经验成熟度。

### 10.1 能力自适应：不压制高置信状态，也不放弃低置信状态

EP5.0 不采用永久的“强模型/弱模型”名单。能力判断是相对于任务族、执行阶段、工具链、
验证器和当前上下文的能力状态，而不是模型名称本身。

例如，同一个模型可能：

- 在代码生成和错误修复上表现稳定；
- 在长流程浏览器操作上容易丢失状态；
- 在正式 PPT 的视觉验收上需要明确检查清单；
- 在开放式研究中检索能力强，但来源边界控制不足。

因此系统使用 `Capability Profile`，而不是一个全局强弱标签：

```text
模型身份
  + Agent 角色
  + 任务族
  + 执行阶段
  + 工具链
  + 验证器
  + 近期可观测结果
  → 当前能力状态
```

能力状态至少记录四类信号：

```text
success_rate       同类任务通过率
recovery_cost      失败后的重试次数、耗时和 Token
verification_gap   自称完成与实际验证结果的差距
transfer_quality   经验迁移到新任务或新环境后的效果
```

能力状态还要带样本量、时间范围、置信区间和新鲜度。只有一两次成功或失败，不能改变
模型的干预策略。

```text
高置信的任务局部能力状态
  → 只给短的候选提醒和适用条件
  → 允许 Agent 自己选择路线
  → 不重复解释基础步骤

能力证据不足或出现明确错误信号
  → 给一条主修复路线和一条备选路线
  → 附带验证方法和停止条件

任务复杂、验证缺口扩大或连续失败
  → 提供分阶段操作骨架
  → 暴露关键前置条件、检查点和常见陷阱
  → 每个阶段等待确定性验证结果
```

这三种模式不是由模型名称硬编码决定，而是由以下信号动态估计：

- 当前任务复杂度；
- Task Contract 的未决字段数量；
- 当前 Agent 已经出现的失败次数和失败类型；
- 最近相似任务的成功率；
- 工具和验证器是否可用；
- 当前模型在同类任务上的历史成功率；
- 当前回答的置信度和证据完整度。

因此，未来能力提升不会被旧经验过度约束；证据不足的任务状态也可以获得更多结构化帮助。

### 10.1.1 能力分层不是竞赛排名

系统内部可以使用能力状态来决定提示强度，但不向用户展示简单的“模型排名”或永久的
“强模型/弱模型”标签。
实际使用三个状态带：

```text
independent       当前任务已有足够能力，默认只给必要条件和验证要求
assisted           存在不确定性，给少量过程经验和检查点
scaffolded         已出现连续失败或能力缺口，给分阶段骨架和明确停点
```

状态由当前任务动态计算，可以在同一回合中变化。下面的失败次数只是示例，不是固定产品
阈值；实际切换应由可配置策略结合置信度、失败严重性、验证器质量和任务预算决定：

```text
开始时 independent
  → 达到当前策略设定的失败证据门槛
  → 切换 assisted
  → 仍无法定位根因
  → 切换 scaffolded
  → 验证通过后回到 independent 候选状态
```

状态切换只影响过程记忆的读取数量和表达方式，不改变用户事实、权限和当前任务目标。

### 10.1.2 未来模型的兼容方式

新模型接入时不需要人工先判断它是强还是弱。系统先建立“任务局部能力未知”的冷启动状态：

1. 读取少量高置信、低干预的 `hint`；
2. 观察测试、工具结果和验证器反馈；
3. 按任务族建立能力样本；
4. 根据实际收益调整读取强度；
5. 到达样本门槛后才允许使用 `recommend` 或 `scaffold`；
6. 模型版本更新后建立新 Profile，旧 Profile 仅作为迁移参考。

模型在某一任务族上表现更稳定时，过程记忆可以减少该任务族的干预；模型在另一任务族、
新的工具链或发生环境变化时，仍可保持较高辅助。这里的“变强/变弱”只描述有证据支持的
局部能力变化，不推导全局排名，也不把一次升级后的结果传播到其他任务族。这样记忆机制
不会成为未来模型能力提升的上限。

### 10.1.3 能力校准任务

系统需要维护一组小型、可重复且可版本化的能力校准任务，而不是依赖模型厂商描述。下面
只是首批校准域，不是永久测试清单；校准注册表还应记录任务来源、难度、工具依赖、是否
已被训练/提炼数据使用，以及保留测试集归属：

- 代码：编译、单元测试、回归和错误定位；
- 文档：结构检查、分页、字体、渲染和视觉核对；
- 研究：来源选择、主体消歧、冲突保留和引用；
- 网页：状态读取、控件操作、失败恢复和回执；
- 检索：Recall/Research 路由、范围控制和原文回读；
- 协作：任务状态、交接、并行结果合并和去重。

每次校准都生成独立的 `capability_observation`，只更新对应任务族和阶段，不把局部
表现扩散成全局结论。校准任务与记忆提炼任务必须避免数据泄漏；若同一轨迹既参与经验
生成又参与能力验收，结果只能标记为开发信号，不能作为迁移或晋升证据。

### 10.2 记忆的干预等级

每条 Agent Process Memory 要带 `intervention_level`：

```text
observe       只记录，不展示给 Agent
hint          给出一句提醒和适用条件
recommend     给出主路线、备选路线和验证方式
scaffold      给出分阶段任务骨架和检查点
guard         只有确定性风险或明确权限规则才能阻止动作
```

对尚未校准或仅有候选证据的经验，默认最高只能到 `hint`。当任务局部能力画像、经验成熟度、
适用条件和验证策略满足策略门槛后，可以自动选择 `recommend` 或 `scaffold`；`guard` 仍然
只能由确定性风险、权限规则或明确的执行门触发。过去的失败经验不能自行变成拦截规则。

### 10.3 能力画像不等于模型评分

系统不建立一个简单的“模型强弱分数”来决定所有读取。能力画像应按任务族和阶段拆分：

```text
coding_planning
coding_debugging
document_structure
document_visual_qa
research_source_control
browser_state_tracking
retrieval_scope_control
tool_parameter_accuracy
delivery_verification
```

同一个模型可能擅长代码调试，却不擅长 PPT 视觉验收；也可能在分析阶段强，但在长流程
工具协调阶段弱。经验读取必须匹配能力槽位，而不是把全局分数当作判断依据。

### 10.4 迁移与退化处理

Agent Process Memory 在不同模型之间迁移时经过四个状态：

```text
unknown       尚未测试迁移
candidate     语义上可能适用，但没有验证
verified      在新模型和新环境中验证通过
blocked       明确不适用或引入错误
```

模型升级、工具链变化、项目迁移或验证器变化都会触发重新评估。旧经验保留为历史版本，
不会因为新模型出现就自动删除，也不会因为旧模型曾经有效就自动继续指导新模型。

## 11. 冲突、优先级与协同协议

### 11.1 运行时优先级

EP5.0 的运行时优先级固定为：

```text
当前用户 Prompt
  > 当前项目/Session 明确约束
  > 当前 Task Contract
  > 确定性工具和验证器结果
  > 原始来源和 Facts / Experiences
  > 已验证的 Agent Process Skill
  > 条件化 Preference
  > Scenario Summary 和 Mental Model
  > 未验证候选与历史建议
```

这不是所有内容的真实性排序，而是当前行动决策的覆盖顺序。原始来源仍然是事实核验
的最高证据；Preference 和 Skill 只能在其适用条件满足时参与决策。

### 11.2 冲突类型

系统需要区分不同冲突，不能统一叫“记忆冲突”：

- `fact_conflict`：两个来源对同一事实的说法不同；
- `scope_conflict`：同名项目、Session 或文件范围不同；
- `temporal_conflict`：旧状态和新状态不同；
- `preference_conflict`：全局偏好与当前项目偏好不同；
- `skill_conflict`：两条过程经验给出不同路线；
- `model_conflict`：同一技能在不同模型上表现不同；
- `verification_conflict`：Agent 声称完成，但测试或用户验收未通过；
- `source_conflict`：摘要、RAG、Bank 和原始来源不一致。

不同冲突使用不同处理方式：事实冲突回到来源和时间；偏好冲突按范围和当前 Prompt；
Skill 冲突按模型、任务族、成功率和最近验证时间；验证冲突优先采用确定性结果。

### 11.3 记忆融合不是文本拼接

一次任务的上下文包不应把 Facts、Preferences、Scenario、Skill 和 RAG 片段直接拼成
一段长文本，而应带有显式来源槽位：

```json
{
  "task_context": {"objective": "...", "constraints": []},
  "user_guidance": [],
  "scenario_context": [],
  "agent_process_hints": [],
  "historical_evidence": [],
  "external_references": [],
  "verification_requirements": [],
  "unresolved_conflicts": []
}
```

Agent 可以看到它们，但每个槽位的证据角色和行动权限不同。这样可以减少“旧 Skill 被
误读成用户要求”“RAG 文档被误读成个人事实”“情境摘要被误读成原文”的问题。

### 11.4 共享和隔离

Agent Process Memory 默认按 `agent_role + task_archetype + compatibility_profile` 隔离，
只有 `generalized` 且经过迁移验证的 Skill 才能跨 Agent 共享。Project 和 Session 关联
用于解释经验来源，不代表自动共享权限。

用户可以关闭 Agent Process Memory 的记录、检索和注入开关；关闭后 EP5.0 的用户事实、
经历、实体、偏好、情境摘要和外部 RAG 行为不应被改变。

检索顺序建议是：

```text
同 Agent + 同模型 + 同工具链
  → 同 Agent 角色 + 同类模型
  → 同任务类型 + 高置信通用策略
  → 保留适用性未知，不强行注入
```

这里的“同类模型”不能只由厂商、名称或版本字符串推断，必须同时满足能力指纹、工具协议、
验证器和环境条件的兼容检查。若兼容证据不足，经验仍可作为未采用的候选显示，但不得进入
默认注入。

一个模型产生的程序经验可以帮助另一个模型，但迁移必须经过重新验证；单一模型的失败经验
不能直接限制另一个模型。模型升级后，旧经验进入重新评估队列，而不是自动失效或自动继续
生效。经验迁移默认先以 `hint` 形式出现，达到迁移策略的证据门槛后才能升为更强的干预等级。

跨模型读取还必须经过 `transfer_scope.transfer_status` 门控：`candidate`、`unknown` 或缺失状态
只能作为未采用候选，`verified` 才能进入目标模型的默认提示包，`blocked` 必须拒绝。模型、工具链、
验证器或环境发生变化时，可通过 `revalidate_agent_process_memory` 将记录置为
`revalidation_required` 或 `deprecated`；恢复为 `stable` 必须附带独立验证证据，并保留状态变更历史。

跨模型和过程记忆效果必须通过 `evaluate_agent_process_memory` 做确定性 A/B 对照，至少记录失败率、
恢复时间、工具调用、过程记忆 Token 成本和负迁移率。评测工具只读，不负责晋升 Skill；只有达到
样本门槛且负迁移低于策略阈值时，迁移状态才可进入 `verified`。

过程技能发布采用 `shadow → canary → publish` 的隔离流程。`shadow` 只观察，`canary` 只对指定
`experiment_id` 可见，默认检索和其他实验不可见；`publish` 必须通过真实任务的成对回执和独立
验证器门控。任何负迁移、验证失败或环境漂移都可以执行 `rollback`，撤回只改变可见状态，不删除
原始记录和历史状态。

## 11. 数据治理和安全边界

- Raw Trajectory 默认只作审计和离线提炼，不直接进入上下文；
- 过程记忆必须遵守部署环境的数据分类和授权策略。个人私有部署可以在明确授权下保留
  私有过程内容，但导出、发布和跨 Bank 共享前必须经过脱敏/权限过滤；公开发行包不得携带
  私有轨迹、凭据或未经授权的文件内容；
- 通过用户任务、工具输出或测试结果写入的内容必须保留来源和权限范围；
- Project 关联不能自动暴露其下所有 Session；
- 失败经验支持过期、撤销、降级和反例；
- 任何 Agent 过程记忆都不能绕过 EP 的权限和执行门；
- 过程记忆不会反向改写用户 Facts、Experiences 或 Preferences。

## 12. 评测指标

5.0 不能只测“记忆命中了多少条”，还需要测 Agent 行为是否改善：

| 指标 | 说明 |
|---|---|
| Failure Recurrence | 同类错误再次出现的比例 |
| Time to Recovery | 从首次错误到验证通过的耗时 |
| Tool Waste | 无效工具调用和重复调用数量 |
| Verification Quality | 是否真正执行了对应验证器 |
| Transfer Success | 经验迁移到另一模型/任务后是否仍有效 |
| Negative Transfer | 经验迁移后相对无记忆基线造成的退化比例 |
| False Guidance | 过程记忆导致错误行动的比例 |
| Context Cost | 过程记忆带来的 Token 和延迟 |
| Skill Stability | Skill 在多个版本和环境中的成功率 |

最小评测集应同时包含：代码 Bug、PPT/文档交付、RAG 检索、网页操作、模型切换、
工具失败、重复错误和项目跨 Session 延续。每个任务都需要 Preference Off、Agent
Process Memory Off、两者开启三组对照。

### 12.1 能力不伤害测试

除了“低置信任务状态是否获益”，还要专门测试“高置信任务状态是否被拖累”：

```text
high-confidence profile + no process memory
high-confidence profile + hint only
high-confidence profile + recommendation

low-confidence profile + no process memory
low-confidence profile + hint / scaffold
```

验收要求：

- 高置信任务状态开启过程记忆后，不能明显增加不必要步骤、Token 或错误率；
- 低置信任务状态开启适用经验后，失败率和恢复时间应改善；
- 不相关 Skill 的误注入率必须低于设定阈值；
- 同一失败经验不能造成下一轮固定重复动作；
- 任务变化后，系统能够放弃过时经验；
- 经验读取失败时，Agent 仍可以走 EP5.0 原有用户记忆路线。

### 12.2 记忆效用归因

系统要尽量记录“这条过程经验是否真的有帮助”，但不把模型内部注意力伪装成因果证明。
可以使用以下可观测信号：

- 读取前后的工具调用数量；
- 修复时间和重试次数；
- 确定性测试结果；
- 用户是否要求返工；
- 同类任务的再次失败率；
- Agent 是否主动选择了记忆中的验证器或停止条件。

最终仍应把 `memory_visible`、`memory_candidate_selected`、`outcome_improved` 和
`causal_proof` 分开。没有独立对照时，`causal_proof` 保持未知。

## 13. 版本实施路线

### 5.0-A：只读采集和审计

- 统一 Agent、Model、Tool、Task、Trajectory 标识；
- 捕获工具调用、错误、测试和验证结果；
- 不自动提炼、不影响当前回答；
- 建立原始轨迹查看和时间线。

### 5.0-B：Failure Episode

- 增加失败类型和根因候选；
- 关联 Project、Session、Model 和 Tool；
- 建立候选区和人工/规则审核状态；
- 在控制台增加 Agent 过程星座图。

### 5.0-C：Repair Pattern 和受控读取

- 从验证通过的失败修复中提炼 Repair Pattern；
- 任务开始前和工具失败后按需读取；
- 加入模型适用范围和过期机制；
- 与现有 Recall/Research/Scenario Summary 统一路由。

### 5.0-D：Procedural Skill

- 多次验证后晋升为 Skill；
- 支持版本、替代方案、反例和成功率；
- 建立跨模型迁移评测；
- 在不影响 EP5.0 默认行为的情况下逐步启用。

### 5.0-E：能力自适应和跨模型迁移

- 建立按任务族和阶段的能力画像；
- 支持 `hint / recommend / scaffold / guard` 干预等级；
- 建立高置信任务状态不受过度指导、低置信任务状态获得帮助的 A/B 测试；
- 记录跨模型迁移状态和重新验证队列；
- 支持 Skill 的降级、撤销、替代和回滚。

### 13.1 推荐的数据契约

Agent Process Memory 的统一外层记录建议如下：

```json
{
  "process_memory_id": "pm_...",
  "schema_version": "agent-process-memory.v1",
  "taxonomy_version": "task-archetype.v1",
  "dimension_registry_version": "process-dimensions.v1",
  "kind": "trace|event|episode|pattern|skill",
  "task_archetype": ["software_engineering"],
  "process_dimensions": ["debugging", "verification"],
  "phase": "recover",
  "outcome": "recovered",
  "maturity": "verified",
  "intervention_level": "hint",
  "primary_context": {"project_id": "...", "session_id": "..."},
  "related_contexts": [],
  "agent": {"role": "coding-agent", "host": "codex"},
  "outcome_attribution": [],
  "model_profile": {},
  "model_capability_fingerprint": {},
  "environment_fingerprint": {},
  "modality_profile": {},
  "evaluation_set_version": "...",
  "drift_status": "stable|watch|revalidation_required|deprecated",
  "toolchain": [],
  "preconditions": [],
  "failure_signature": [],
  "repair_actions": [],
  "verification_evidence": [],
  "transfer_scope": {},
  "selection_exposure": {"shown": 0, "selected": 0, "skipped": 0},
  "counterevidence": [],
  "supersedes": [],
  "source_trace_ids": [],
  "created_at": "...",
  "last_verified_at": "...",
  "revalidation_due": "..."
}
```

字段可以逐步扩展，但 `schema_version`、`taxonomy_version`、`dimension_registry_version`、
`kind`、`task_archetype`、`phase`、`maturity`、`intervention_level`、`model_profile`、
`source_trace_ids` 和 `verification_evidence` 是第一版必须保留的稳定语义骨架。新增字段
必须向后兼容；未知字段应保留并标记，不能在迁移时静默丢弃，也不能把新枚举强行映射成
旧枚举。

## 14. 验收标准

5.0 通过验收至少需要证明：

1. 能完整保存一次 Agent 失败和修复过程；
2. 能识别失败发生的阶段和工具；
3. 能把成功修复与原失败关联起来；
4. 未验证的经验不会进入默认注入；
5. 同一错误在第二次任务中能检索到对应修复提示；
6. 不相关项目和不同模型的经验不会误注入；
7. 模型切换后会按适用范围和重新验证状态处理旧经验；
8. Agent 过程记忆能和 Project、Session、Facts、Experiences、Entities、Preferences
   建立关系，但不会互相覆盖语义；
9. 星座图、图谱、表格和时间线都能展示 Agent 过程节点及其来源；
10. 关闭 Agent Process Memory 后，EP5.0 原有用户记忆链路仍能正常运行。

## 15. 结论

EP5.0 最适合采用“用户记忆维度 + Agent 过程记忆维度 + 共享证据关系图”的架构。
Agent 可以作为 Experiences 的主体继续保留，但失败、修复和程序技能要进入独立的
Agent Process Memory，以便控制写入质量、模型适用范围和读取时机。

这样，EP 不只知道“用户做过什么”，还知道“Agent 怎样做过、哪里走错、怎样修好、
以后什么情况下应该提前避开”，同时保留证据、版本和权限边界。

## 16. 最终泛化审查与长期演进规则

本节专门检查 PRD 是否会对未来模型、未来任务和未来工具形成过度约束。

### 16.1 当前发现的过拟合风险

#### 风险一：任务族清单过早固化

Software Engineering、Document、Research 等任务族适合首版落地，但未来可能出现
新的混合任务，例如“研究 + 代码 + 外部 RAG + 网页操作”。因此任务族必须是可版本化
的开放词表，不允许把首版 11 个任务族写成永久枚举。

约束：

- 保留 `other` 和多任务组合；
- 新任务连续出现并跨多个 Project 后，才考虑建立新任务族；
- 新任务族必须有迁移样本、提炼模板和回归集；
- 任务族定义更新时保留旧版本映射，不能让旧记忆失去可读性。

#### 风险二：过程维度数量可能变成新的固定框架

Planning、Tool Use、Debugging 等是稳定骨架，但未来 Agent 可能出现新的能力环节，
例如多 Agent 协议、长期自主规划、环境建模和自我评测。

约束：

- 核心维度只负责第一层导航；
- 具体能力使用可扩展的 `process_tags`；
- 标签要记录来源、出现次数、任务覆盖和审阅状态；
- 新标签不能仅因一次异常自动升级为系统维度。

#### 风险三：Capability Profile 可能被稀疏样本误导

一次成功不代表模型强，一次失败也不代表模型弱。能力画像必须带：

```text
sample_count
time_window
confidence_interval
task_distribution
verifier_quality
data_shift_status
```

样本不足时保持 `unknown`，使用保守的低干预策略，不用猜测值替代未知。

#### 风险四：经验记忆形成闭环污染

Agent 读取旧经验后成功，系统可能把“遵循旧经验”误认为“旧经验正确”；错误经验
因此会自我强化。

约束：

- 记录经验是否被读取、是否被采用、结果是否改善三个独立字段；
- 对照任务必须允许不读取该经验；
- 技能晋升需要跨任务或跨环境复现；
- 经验的成功不能只依赖同一个 Agent 或同一个评估器；
- 保留反例和失败样本，不能只保存成功版本。

#### 风险五：把“更聪明”误写成“更少记忆”

高置信任务状态可能不需要步骤性指引，但仍然可能需要项目情境、用户约束、来源证据和过去的
失败提醒。读取强度应按记忆种类分别调整：

```text
过程脚手架：任务局部能力有充分证据时减少
用户硬约束：不能因为任务局部能力证据充分而减少
来源证据：按事实缺口读取
安全和权限规则：始终遵守
情境摘要：按指代和范围需要读取
```

能力自适应只调整 Agent Process Memory 的干预强度，不能削弱用户约束、权限或事实核验。

#### 风险六：评测集泄漏导致的虚假泛化

如果校准任务、回归集和过程记忆来自同一批 Project 或 Session，系统可能只是记住了测试
表面的路线，而没有学到可迁移的条件。评测数据必须按时间、项目和任务来源分离提炼、调参、
验证和保留测试集；同一来源的重复轨迹、派生摘要和相似模板不能同时出现在提炼集和最终
验收集。验收至少要包含未见过的任务组合、工具链变化和模型迁移，并报告覆盖边界。

#### 风险七：在线更新把短期波动写成长期能力

连续任务中的局部成功、用户一次性表扬或某个评估器的偏差，都可能让 Skill 过快晋升。在线
更新必须经过候选区、影子运行或小范围 Canary，再按独立验证、反例和回滚条件决定晋升；在
晋升窗口内只影响当前实验流，不改变默认检索。任何撤销都保留原版本和触发原因，避免为了
追求最新而丢失可追溯性。

#### 风险八：上下文预算把相关性误当成价值

更长的过程记忆不一定更有用。系统应分别记录相关性、证据质量、预期收益和 Token 成本，
以任务预算动态选择注入内容；用户硬约束、权限和来源证据不能因预算不足被过程 Skill 挤出。
预算策略本身也要版本化和可回退，不能用一个全局固定条数适配所有任务。

#### 风险九：语义漂移与流程漂移被误当成正常成长

持续摘要可能逐步改变事实含义，持续修订的 Skill 也可能把偶然绕路固化成标准流程。系统
必须同时监测 `semantic_drift` 和 `procedural_drift`：保留原始版本、摘要差异、触发证据和
反例；当新版本改变关键条件、主体、时间、验证器或失败边界时，先降级到候选/影子版本，
不能仅因“更新更近”就替换旧版本。选择性遗忘应由冲突、撤销、权限和明确的删除策略触发，
不能只按时间自动删除仍有证据价值的历史记录。

### 16.2 面向未来模型的兼容协议

未来模型可能不再只输出文本，可能支持原生规划、结构化工具调用、多模态状态、内部
验证、可执行计划或更强的长期上下文。EP5.0 不应假定所有模型都使用同一种提示方式。

因此 Agent Process Memory 的交付协议应抽象为：

```text
Memory Hint Packet
  - applicable_when
  - avoid_when
  - suggested_checks
  - optional_actions
  - evidence_links
  - confidence
  - intervention_level
  - expiry / revalidation
```

宿主或模型可以选择把它转换成：

- 文本提示；
- 结构化计划约束；
- 工具前检查项；
- 评估器输入；
- 代码或文档模板；
- 模型原生 memory slot。

EP 只维护语义和证据，不把当前模型的 Prompt 格式当成永久协议。

### 16.2.1 过程草稿与缓存复用

过程记忆摘要优先由当前 Agent 在任务结束前主动提交，前提是本轮确实出现错误、绕路、
回退或多次尝试，并且已经得到验证成功。系统不要求每轮额外调用模型生成总结；Agent
无法生成草稿时，保留原始轨迹即可。

若宿主的 Stop/SessionEnd Hook 支持继续当前回合，可以在一次有限的补写机会中要求 Agent
输出结构化 `Process Brief`，但必须带防循环标记和超时上限。补写失败、超时或宿主不支持
继续时，直接结束任务，不影响回答和 EP5.0 写入。

当当前 Agent 与后续总结使用同一模型服务、稳定的开发者说明、工具定义和缓存键时，服务端
可能复用相同的提示前缀；跨 Codex 原生模型服务与 EP Coding Plan 的请求不能假定共享缓存。
缓存命中必须以服务返回的 `cached_tokens` / `cache_write_tokens` 等真实用量为准。缓存只是
成本和延迟优化，不能成为过程记忆正确性的前提。

### 16.3 经验的探索与利用平衡

如果每次都只使用已有 Skill，Agent 会被旧路线锁定；如果每次都完全探索，历史经验
又无法减少成本。因此 5.0 需要保留三种执行意图：

```text
exploit       优先采用高置信、已验证经验
explore       有意尝试新路线并记录过程
compare       同时保留两条候选路线，比较结果
```

探索任务的结果不能直接覆盖现有 Skill。它先进入候选轨迹，经过验证和重复测试后再
更新过程记忆。这样系统可以持续成长，又不会因为一次新尝试破坏已有稳定流程。

### 16.4 经验遗忘和降级

过程经验会因模型、工具、依赖、项目规则和用户要求变化而失效。每条 Pattern/Skill
需要支持：

- 时间衰减；
- 最近验证时间；
- 失败反例数量；
- 环境变更影响；
- 手动撤销；
- 自动降级；
- 替代版本；
- 再验证队列。

降级后的经验不删除，保留为历史记录，并从默认检索降到故障审计或明确历史查询。

### 16.5 防止单一评估器成为新的瓶颈

代码可以依赖编译器和测试，文档可以依赖结构检查和渲染，网页可以依赖状态回执，
开放式研究和表达任务则可能需要模型评估或用户反馈。评估器本身也可能有偏差。

因此验证证据应标记 `verifier_kind` 和可信度：

```text
deterministic_tool
automated_test
render_or_visual_check
source_check
user_acceptance
model_judge
agent_self_report
```

`agent_self_report` 不能单独晋升 Skill；`model_judge` 需要独立模型、抽样复核或
确定性信号支持。不同评估器冲突时保留冲突，不把一个评分直接当作真值。

### 16.6 长期成长的更新循环

EP5.0 的成长循环最终应是：

```text
执行轨迹
  → 观察结果
  → 错误/成功定位
  → 形成候选经验
  → 按任务族和阶段归类
  → 验证和反例检查
  → 评估模型适用范围
  → 小范围试用
  → A/B 比较
  → 晋升、保持、降级或撤销
```

这个循环允许模型变强、任务变复杂、工具不断变化，同时让记忆系统保持可解释、可回退、
可迁移和可审计。

### 16.7 历史候选技能的可见性与发布门

历史会话可以通过重复的失败形状、恢复阶段和验证信号形成“候选程序技能”，但历史扫描本身
不能证明这些步骤在新任务上有效。因此实现允许写入 `kind=skill`、`status=candidate`、
`maturity=diagnosed`、`rollout_state=shadow` 的候选记录，用于智能体记忆页面的图谱、表格和
时间线展示。候选记录必须标出来源模式、任务族、过程维度和“仅形状证据”说明；它们不能进入
普通 `search_agent_process_memory`，不能注入当前任务，也不能改变能力画像。

候选技能要经过至少一个未参与历史提炼的新任务、独立验证器和适用范围检查，随后再进入
`replicated`/`verified` 的正常晋升路径。候选数量与已发布技能数量在界面分开展示，避免把“有
历史线索”误读成“已有可复用技能”，也避免安全门控让历史提炼结果看起来完全为空。

### 16.8 审查结论

当前 PRD 的稳定语义契约是：初始记忆平面、P0–P4 过程层、Task Contract、能力画像、
干预等级、证据成熟度和冲突协议。它们的字段含义与边界需要保持兼容，但平面数量、过程层
映射、任务族清单、过程标签、模型能力样本和 Skill 集合都属于可演进数据，不能写死成
产品永久结构。

5.0 实施时应先做只读轨迹采集和评估，再逐步启用受控读取；任何自动提炼和自动晋升都
必须经过来源、验证、迁移和反例检查。这样既能让证据不足的任务状态获得帮助，也能让
未来能力提升的模型保持自主判断空间。

### 16.9 过程策略不是 Skill 集合

EP5.0 的核心不是把每次执行都压缩成一个固定 Skill。`skill` 是为兼容外部 Runbook、技能
库或明确要求的可执行流程而保留的技术类型，只在过程模式已经经过重复验证、适用范围清楚且
确实适合压缩成固定步骤时使用。它不是 Agent Process Memory 的默认终点，也不代表 EP 的
全部智能。

默认运行时应优先使用动态的过程提示包：根据当前任务族、阶段、模型能力、工具链、项目/Session
情境、失败反例和验证器质量，临时组合必要的观察、提醒、建议或阶段骨架。候选模式可以保持
为 `pattern`、能力画像或条件化过程策略，而不必晋升为 Skill。只有在需要导出固定 Runbook、
跨系统共享或用户明确要求时，才把已验证的策略投影为 `kind=skill`。

Web 端默认称其为“可复用过程策略”，并区分候选、已验证、已迁移和已降级；底层 `skill` 键
继续保留以保证数据和 MCP 向后兼容。

### 16.10 自动提炼与自动晋升

过程记忆的日常提炼不得依赖用户或开发者逐条人工校准。每次真实工具轨迹完成后，系统应在
后台根据独立验证器回执自动执行：

```text
真实轨迹
  → 验证回执检查
  → 自动 Failure Episode
  → 跨任务相似模式聚合
  → 候选过程策略
  → 迁移、负迁移和漂移评估
  → 自动 shadow / canary / publish / rollback
```

“独立验证”指测试、编译、渲染、来源核验、工具回执或受控模型评估等机器可检查证据，不是
人工确认。没有独立证据的轨迹仍会保存为观察，但不能自动升级。正式策略的发布由样本量、
跨任务覆盖、验证成功率、负迁移率和漂移门控共同决定；人工只能作为可选的撤销或覆盖入口，
不能成为日常运行的前置条件。

## 17. 公共命名与 Agent Recall / Agent Research 模式

### 17.1 命名空间

EP5.0 对外显示名称统一采用“主体 + 动作”格式：

```text
User Recall / 用户召回
User Research / 用户研究
User Preference / 用户偏好
User Scenario Summary / 用户情景摘要
User Source Readback / 用户原文回读

Agent Recall / 智能体召回
Agent Research / 智能体研究
Agent Guidance / 智能体指导
Agent Observe / 智能体观察
Agent Writeback / 智能体写回
Agent Evaluation / 智能体评估
```

稳定公共键为 `user_recall`、`user_research`、`user_preference`、`agent_recall`、
`agent_research`、`agent_guidance`、`agent_observe`、`agent_writeback` 和
`agent_evaluation`。现有 MCP 与内部键继续作为兼容别名，避免破坏旧 Hook、客户端和历史回执。

### 17.2 两种过程检索模式

`Agent Recall` 是当前任务定向的低延迟过程经验检索：识别任务族和过程维度，召回失败事件、
修复模式、程序技能和反例，再经过模型、工具链与环境兼容性门控，形成 Guidance Packet。

`Agent Research` 是跨过程图谱的高阶研究模式。它沿 Agent、Model、Tool、Task、Session、
Project、Failure、Repair、Pattern、Skill 和验证器关系做多跳分析，用于判断重复失败的根因、
修复模式的泛化性、模型迁移、工具迁移、负迁移和经验过期。它必须返回证据路径、竞争假设、
反例、适用范围和未决项，不能直接把研究结论晋升为 Skill 或全局约束。

### 17.3 触发规则

```text
简单或自足任务                    → 不调用
普通复杂执行任务                  → Agent Recall
跨任务/跨项目/因果/迁移问题         → Agent Research
Recall 候选冲突或范围不足           → Agent Research
经验泛化、模型能力和工具迁移评估    → Agent Research
```

复杂问题可以直接进入 Agent Research，不强制先执行 Agent Recall。两者都必须保留真实回执，
并分别记录候选、返回、送达、证据路径和未决状态。

## 18. 过程记忆路由可观测性契约

所有过程记忆路线统一记录：

```text
route_required → route_started → hook_started/tool_called
→ candidates_discovered → returned_to_host → delivery_state
→ source_readback → answer_use/unresolved
```

Hook 自动注入必须产生 `evolving_profile_agent_process` 回执，并绑定 `session_id`、`turn_id`、
`hook_invocation_id` 和 `prompt_id`。链路页没有 Prompt 绑定回执时，不得按时间或全局记录猜测。

为兼容旧链路投影而保存的过程回执必须标记为 `route_receipt`，并从过程记忆检索中排除，防止
审计投影反向污染 Agent Recall。
