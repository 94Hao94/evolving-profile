# Evolving Profile 4.0

Evolving Profile（EP）是面向 AI Agent 的长期记忆与证据控制平面。它把“记忆如何
记录、偏好如何形成、情境如何补充、历史何时读取、原文如何核验、宿主是否收到”
拆成一条可解释、可配置、可审计的运行链路，而不是把一次相似度搜索直接当成答案。

本发行包是脱敏、可重新初始化的模板，不包含个人 Bank、对话、API Key、宿主
会话或生产回执。默认 Bank 为 `personal-memory`，接收者安装后创建自己的空
Bank，再导入自己的资料。

作者：CCY，EP 4.0。感谢 Hindsight 项目及相关公开研究提供的思路和工程背景。
EP 4.0 在 EP 3.0 的入口、证据和审计基础上，增加了情境摘要、外部 RAG、检索模型
档案、可选 JEV 判断器、模块化配置和备份策略。致谢与边界见 [NOTICE.md](NOTICE.md)。

## 版本定位

4.0 是一次运行能力升级，不是简单改名。它保留 3.0 的 Bank、L0/L1/L2、偏好、
证据回读和多宿主审计，同时增加：

- Project / Session Scenario Summary 三层情境摘要；
- 情境不足时按缺口切换到 `read_source` 或原始 Session 回放；
- 外部 RAG，与 EP 内部 Bank 隔离；
- Embedding、Rerank、RRF 的模型档案和索引兼容检查；
- JEV 可选判断器，默认关闭并由规则链托底；
- Provider / Fallback、多维度模块开关和可视化配置；
- 备份目录、周期、保留和自动清理策略；
- Preference 自适应候选预算与统一星座图视觉；
- `get_preference`、`read_preference_unit`、`search_scenario_summary` 等统一工具名。

版本更新记录见 [CHANGELOG-4.0.md](CHANGELOG-4.0.md)；3.0 历史见
[CHANGELOG-3.0.md](CHANGELOG-3.0.md)。
后续版本的脱敏同步、贡献者核对、测试和 GitHub PR 流程见
[发布手册](docs/RELEASING.md)；已核实的发布历史见 [发布记录](docs/RELEASE-LEDGER.md)。

## EP4.0 新增能力的运行逻辑

### 情境摘要：先解释环境，再决定是否回到原文

EP4.0 把 Project、Session/Conversation 作为与事实、经历、实体和偏好并行的情境维度。
情境摘要只负责解释“这条记忆属于什么环境”，不替代事实证据。

```text
情境候选
  → compact：快速定位
  → standard：补充过程、约束和阶段
  → full：更完整但仍然压缩的情境摘要
  → 仍有缺口时，按缺口选择 read_source 或原始 Session 回放
```

事实、金额、版本、人物和状态优先回到 `read_source`；需要原话、争议过程或完整修改
轨迹时才读取有界的原始 Session；需要跨多个会话的项目演变时，才按 Project 范围
聚合多个 Session。EP 不会因为摘要不完整就把整个项目历史一次性注入上下文。

### 外部 RAG：与 EP 内部记忆隔离

RAG 是可选的外部资料路线，用于 PDF、Word、Markdown 和其他用户指定目录。它与 EP
内部 Bank 分开检索：

```text
EP Bank：Facts / Experiences / Entities / Preferences
外部 RAG：用户指定的外部文件目录
```

外部 RAG 可以使用词法检索、Embedding、RRF 融合、Rerank、Top-K 和分数门槛；RAG
关闭时不会读取外部目录，也不会把外部资料写进 EP 的长期记忆。Embedding 更换后，
系统会根据索引签名提示是否需要重建，避免新旧向量混用。

### 检索模型与判断模型

EP4.0 将模型分成不同职责：

- Embedding：生成语义向量；
- Rerank：对候选重新排序；
- RRF：融合词法与向量结果；
- 主 Provider / Fallback：负责 EP 的模型调用容灾；
- JEV：可选的证据充分性、来源路由、故障归因和风险判断器。

JEV 不负责 Recall、Research 或事实写入。JEV 默认关闭，关闭或调用失败时由确定性
规则和保守未知状态托底；风险确认门也默认关闭，不会改变普通任务的执行方式。

### Preference：有界、条件化、自适应

`get_preference` 不是全量偏好注入，也不是单纯向量相似度排序。它结合当前任务、
阶段、适用条件、例外和版本生成有限候选。理解/分析类任务默认更少，执行/验证/交付
类任务允许更高上限；候选进入 Agent 上下文不等于 Agent 最终采用。

### 配置、备份与审计

EP4.0 的 Console 将 Provider、Fallback、EP 模块、检索模型、JEV、外部 RAG、备份和
版本信息拆开配置。备份支持位置、每日/每周/月度周期、保留天数、最大套数、最少成功
套数、SHA-256 清单和自动清理；云端镜像与本地备份策略分开管理。

## 一、核心链路

```text
宿主入口
  → 说明书与 L0 地图
  → Get Preference 候选
  → Agent 结合完整任务判断
  → catalog / recall / research
  → 分页与原文核验
  → 送达回执与链路审计
```

EP 不声称知道 Agent 最终“采用”了哪一条记忆；它分别记录看到的内容、工具
返回、来源位置和未核验状态。

这一链路有两个重要责任边界：第一，入口层负责把完整任务、必要前文、阶段和约束
交给 Agent，而不是只拿最后一句短 Prompt 去猜；第二，历史工具只负责返回候选和
来源定位，不能替 Agent 把候选升级为事实。Agent 可以选择不查历史、只查一个主题，
也可以在证据不足时继续 research 和 read_source。EP 的回执会分别记录“没有调用”、
“调用但为空”“返回候选”“已送达宿主”和“尚无法判断答案是否使用”，避免把这些
状态压成一个模糊的成功/失败标志。

这套拆分让系统可以同时服务简单任务和复杂任务：简单问题不会因为记忆系统存在就
强行注入大量内容；复杂问题则可以从 L0 开始逐层进入 L1、L2，并保留可回读路径。

## 二、记忆对象

- **Facts（事实）**：来源支持的事实、状态、规则和约束。内部兼容字段可能仍
  使用 `fact_type=world`，这是 schema 兼容名，不代表只记录外部世界。
- **Experiences（经历）**：带主体、时间、情境、过程、结果和来源的事件。
- **Entities & Relations（实体与关系）**：人、组织、学校、项目、系统、Agent、
  文件和它们的别名、关系、时间与证据范围。
- **Observations（观察）**：从多条独立证据归纳出的模式、偏好、因果或风险。
- **Multi-dimensional Preferences（多维度偏好）**：沟通、解释、决策、执行、
  交付、权限和验收规则。
- **Mental Models（融合心智模型）**：带来源、边界和版本的高阶解释框架。

经历尽量关联主体和实体，但证据不足时保留未知；不能为了图谱完整而强行合并。

这些对象不是并列的几个“文本分类文件夹”，而是不同证据语义：Facts 更关注某个
状态、规则或命题是否成立；Experiences 关注谁在何时经历了什么过程和结果；Entities
提供跨记录的稳定对象；Observations 从多条记录归纳模式；Preferences 把经过审阅、
带条件和例外的协作要求暴露给 Agent；Mental Models 负责更高层的解释框架。派生方向
原则上是：

```text
Sources → Facts / Experiences → Observations → Preferences / Mental Models
```

上层内容不能反过来覆盖底层来源。偏好可以作为协作参考，但不能授权危险动作，不能
压过当前用户要求，也不能在没有来源和范围的情况下改写事实。实体关系同样要保留
来源、时间和消歧状态：一个实体可以参与多条经历，一条经历也可以涉及多个实体，
但实体连线本身不代表关系已经被原文证明。

### Observation 与 Preference 的关系

Observation 不是多维度偏好的同义词，而是偏好形成前的重要中间层：

```text
原始对话 / 工具结果 / 文件证据
  ↓
事实 Facts 与经历 Experiences
  ↓  多条独立证据、去重、时间和主体核对
Observation 候选（观察候选）
  ↓  适用范围、重复出现、纠错反馈、冲突和来源审阅
多维度偏好候选
  ↓  审核、发布、版本化
Active Preference（当前可用偏好）
  ↓
Get Preference 在相关任务中有界暴露
```

一次行为、一次测试句、助手自己的建议或项目局部要求，都不能直接升级为全局偏好。
候选必须保留来源、主体、任务阶段、适用范围、例外、反例、冲突和最近核验时间。

### 完整运行架构

```text
Host Adapter
  → 说明书、L0、Get Preference、入口回执
EP Controller
  → Guidance Registry、Topic Catalog、Evidence Workspace、Source Reader
  → Entity/Relation Layer、Audit Ledger
Bank / Data Plane
  → Facts、Experiences、Observations、Entities、Sources
Agent Context
  → 已注入内容、recall/research 结果、read_source 核验证据
```

EP 把“候选发现、准入、传输、Agent 可见、回答使用”分开记账。工具返回不等于
Agent 最终采用；没有独立回执时必须保持未知。

## 三、L0 / L1 / L2

```text
L0：轻量地图，提示可能相关的偏好场景、Bank 主题和来源覆盖。
L1：Get Preference 候选、catalog 主题、子主题和来源 ID。
L2：recall 候选、research 工作区、分页结果和 read_source 原文核验。
```

L0/L1/L2 是逻辑读取层，不要求磁盘上有三个同名目录。目录只负责导航，目录
命中不等于事实成立；候选不等于已核实事实。

### L0：每轮总览

L0 使用固定预算列出偏好场景、Bank 主题、实体入口、来源覆盖和新鲜度。它的目的
不是让 Agent 阅读全库，而是帮助 Agent 知道“可能从哪里开始”。L0 可以包含待整理、
覆盖不完整或冲突未计算的标记；这些标记不能被解释为零条记录或没有相关内容。

### L1：目录与候选

L1 包括 Get Preference 返回的偏好候选，以及 `catalog_search` / `catalog_read` 返回
的主题和子主题。L1 提供问题、别名、摘要、范围和 L2 来源 ID。L1 是导航和筛选层，
不是最终事实证据；摘要来自样本或结构投影时，必须保留这一语义边界。

### L2：证据与核验

L2 是 Agent 根据缺口选择的历史候选、research 分页和原文回读。关键结论、冲突、
作者主体、时间变化和字面引文，应从 L2 的 `read_source` 回读。L2 读取也有预算和
分页，不会因为某个主题规模很大就把全部记录一次性注入上下文。

## 四、Get Preference

每轮实质任务入口会自动准备有界候选：

```text
完整 Prompt + 必要前文
  → 适用范围、条件、例外和版本筛选
  → 候选摘要与核心条件进入 Agent 上下文
  → 需要完整正文时 read_preference_unit
```

公开工具名为 `get_preference`，旧的 `get_task_guidance` 只作为隐藏兼容别名。
候选不能覆盖当前 Prompt，也不能授权执行动作。

Get Preference 不是简单的向量相似度接口。入口会根据已审阅 Guidance 条目的适用
条件、例外、状态、版本、任务阶段和当前 Prompt 生成有界候选。高置信候选直接注入
摘要和核心条件；预算之外的候选至少可以保留摘要和适用范围，完整正文则通过
`read_preference_unit` 按 ID 展开。候选进入上下文不等于 Agent 采用它，页面和回执必须
区分“已注入”“可展开”“完整正文已读”和“回答是否使用未知”。

偏好筛选的目标不是每轮凑满固定条数，而是宁可少返回，也不要把没有适用条件的规则
伪装成当前任务要求。另一方面，过于严格的候选筛选也可能漏掉低表面相似度但真正
有帮助的偏好，因此 EP 保留 L0 导航、Agent 主动下钻和按 ID 补读作为召回兜底。

## 五、Bank 目录与证据工具

`catalog_list`、`catalog_search`、`catalog_read` 只做主题导航；`recall` 适合
单点或小范围历史缺口；`research` 适合多主体、多项目、时间线、多跳关系和
关联闭包；`read_research` 用于分页；`read_source` 用于回到原文核验主体、
时间、否定、历史变化和来源范围。

图谱不要求 Agent 每轮读取整张图。Controller/Bank 可用实体、别名、时间和关系
扩展候选，research 适合多跳调查；图谱连线本身不能证明事实。

## 六、与其他系统的定位

EP 4.0 不把“向量相似度最高”当作“当前任务最适用”。它保留完整任务入口、
L0/L1/L2 导航、Agent 主动选择、偏好与事实分离、来源回读、权限和宿主审计。

这不是未经测试的绝对 benchmark 结论：其他系统可能更偏编码项目记忆、通用
长期对话、图谱或反思。EP 的定位是多主体、跨项目、偏好治理和证据审计。

本项目感谢 Hindsight 的 retain/recall/reflect、实体关系和长期记忆研究方向；
EP 4.0 是独立的控制平面和宿主适配实现，不携带 Hindsight 的用户数据或密钥。

### 与常见自动召回方案的工程差异

一些自动记忆集成在每轮 Prompt 前只把当前用户消息作为查询，后台服务再用另一个
LLM 从已保存 transcript 中抽取事实。这样部署简单，但短 Prompt 缺少前文时，
后台抽取模型看不到 Agent 的完整任务目标、隐藏上下文和当前阶段；分块、摘要和
实体解析还可能造成语境丢失。EP 4.0 先提供完整任务入口、L0 地图和有界偏好候选，
再由真正负责回答的 Agent 组织 recall/research 查询，并用 read_source 核验。

这不是“向量一定错误、EP 一定正确”的绝对结论。EP 的工程主张是把查询意图、
偏好判断、证据检索和原文核验拆开，让每一步都有可回读回执；这对多主体、多项目、
跨会话协作和权限隔离更容易审计。AgentMemory 等工具通常更强调编码项目的开箱即用
上下文；EP 更强调跨宿主入口、主体/经历建模、偏好治理和证据链。实际选型仍应使用
自己的问题集做 A/B 评测。

### 公开方案对比：机制、边界与 EP 的应对

下表比较公开集成方式和常见工程取舍，不是宣称所有版本、配置或 benchmark 结果
完全相同。真正选型应在同一模型、同一数据、同一预算下复测。

| 方案/方向 | 典型优势 | 潜在边界 | EP 4.0 的应对 |
|---|---|---|---|
| Hindsight | retain/recall/reflect；事实、经历、实体、时间和关系；适合长期学习型 Agent | 自动 Recall 常以当前消息或 transcript 为入口；后台 LLM 抽取无法天然看到 Agent 的隐藏任务上下文；分块和摘要可能损失语境 | 先提供完整任务、L0 和偏好候选；由回答 Agent 组织 recall/research；关键结论 read_source 回读；单独记录候选、送达和来源 |
| AgentMemory | 面向编码 Agent，跨 Claude Code、Codex、Cursor 等接入方便；项目上下文补全快；也具备实体/图谱和生命周期能力 | 重点通常是项目工作记忆和自动注入；多主体经历、用户偏好治理、证据来源和权限分层的具体实现依配置而定 | EP 同样提供实体、别名、关系、时间和图谱能力，并进一步把主体、来源、范围、偏好治理、权限和宿主审计统一到同一链路 |
| Mem0 类自动记忆 | 产品接入简单，自动提取和召回适合快速原型 | 自动提取的事实、偏好和摘要若缺少强来源治理，容易出现适用范围过宽、旧状态残留或事实与偏好混淆 | Preference、Facts、Experiences、Observations 分层；保留条件、例外、版本、来源和冲突；当前 Prompt 优先 |
| Zep / Graphiti 类时间图谱 | 时间线、实体关系、多跳查询和图结构表达较强 | 图谱能表达关系，不自动证明关系正确；图谱层本身不等于偏好治理、宿主送达或回答使用审计 | 图谱只作导航和候选扩展；关键关系必须有主体、时间、范围和来源，最终 read_source 核验 |
| Letta / MemGPT 类 Agent 管理记忆 | 让 Agent 主动管理工作记忆、长期记忆和上下文 | 记忆质量依赖 Agent 的管理行为；没有独立证据和版本治理时，临时判断可能变成稳定记忆 | Hook 强制提供入口和 L0；Agent 负责路线选择，偏好发布、来源核验和权限由 EP 控制 |

### EP 4.0 的核心优势主张

1. **完整任务优先**：入口可以携带当前 Prompt、必要前文、阶段、约束和任务状态，
   让 Agent 先理解任务，再决定历史缺口。
2. **导航和证据分离**：L0/L1 只用于导航；recall/research 返回候选；read_source
   才是原文核验，不把目录摘要直接当事实。
3. **偏好和事实分离**：Observation 是偏好形成前的候选草稿；Preference 必须经过
   适用范围、例外、重复证据和版本审阅；一次行为不能自动成为全局偏好。
4. **实体能力不是短板**：EP 同样维护实体、别名、关系、时间和图谱；差异在于每条
   关系还要保留主体、范围、来源和核验状态，不把图谱连线直接当成事实。
5. **Agent 决策、系统审计**：Agent 决定是否 recall/research、查哪些范围；EP 记录
   工具调用、候选数量、分页、来源和宿主送达，仍不伪造“Agent 最终采用”。
6. **多宿主一致性**：Codex、Hermes、Claude Code 使用同一工具契约和主 Bank 入口。
7. **权限和数据边界**：个人主 Bank、来源归档 Bank 和专用 Agent Bank 可以分开。

### EP 4.0 的诚实边界

EP 4.0 仍有成本和风险：需要更完整的宿主上下文；Agent 需要遵守目录和证据协议；
目录、候选和偏好筛选仍可能出现误选；多阶段链路比单一向量召回更复杂；本发行包
没有用发布者数据声称公开 benchmark 全面领先。它的优势是可解释、可治理、可回读、
可跨宿主审计，是否更准确应通过接收者自己的问题集验证。

推荐最小评测集：短 Prompt、依赖前文的续问、多主体关系、时间线、偏好冲突、原话
核验、无关候选干扰、权限隔离和空结果。至少比较命中率、误注入率、原文可追溯率、
Token、延迟和宿主可见回执。

### 参考资料

- [Hindsight 官方仓库](https://github.com/vectorize-io/hindsight)
- [Hindsight Codex 集成说明](https://github.com/vectorize-io/hindsight/blob/main/hindsight-docs/docs-integrations/codex.md)
- [Hindsight Hermes 集成说明](https://github.com/vectorize-io/hindsight/blob/main/hindsight-docs/docs-integrations/hermes.md)
- [Hindsight 论文：Hindsight is 20/20](https://arxiv.org/abs/2512.12818)
- [AgentMemory 官方仓库](https://github.com/rohitg00/agentmemory)

| 维度 | EP 4.0 | 常见自动召回集成 | AgentMemory 类编码记忆工具 |
|---|---|---|---|
| 查询入口 | 完整任务 + 前文 + L0 | 常见是当前用户消息或短查询 | 通常是项目/会话上下文 |
| 偏好 | 多维度、条件、例外、版本化 | 往往和历史候选混在一起 | 常偏项目工作习惯 |
| 历史读取 | Agent 选 recall/research，再回读来源 | 系统自动取相似候选 | 重点是快速补全编码上下文 |
| 关系处理 | 实体、主体、时间、范围和来源分开核验 | 取决于后端图谱和配置 | 取决于引擎是否建图 |
| 审计 | 候选、送达、来源和宿主回执分开 | 常主要记录检索结果 | 常主要关注是否补回上下文 |
| 主要代价 | 需要 Agent 理解目录并做路线判断 | 可能短查询误召回或漏召回 | 可能把项目上下文自动带入过多 |

### Hindsight 集成的边界说明

Hindsight 的公开集成通常由宿主 Hook 把当前 Prompt 或会话 transcript 发送给
Hindsight 服务，再由服务端配置的 LLM 做事实抽取、实体解析、时间和关系处理，
之后 Recall 再返回候选。它能工作，也可以配置不同云端或本地模型；但它不天然拥有
Agent 此刻的完整隐藏上下文、任务阶段和未写入 transcript 的意图。

EP 4.0 的区别不是声称 Hindsight “不能检索”，而是把完整任务理解交给真正回答的
Agent：Agent 先看 L0 和 Get Preference，再组织更完整的 recall/research 查询，
最后用 read_source 做证据核验。这个设计更适合跨主体、跨项目和需要解释“为什么
这条偏好适用”的场景。

## 七、安装与 API Key

```bash
cp .env.example .env
# 编辑 .env，填写自己的 provider、model、base URL 和 API Key
./scripts/verify-package.sh
```

### 7.1 支持环境

发行包按下列基线验证：

| 组件 | 最低建议 | 用途 |
|---|---|---|
| macOS / Linux | macOS 13+、Ubuntu 22.04+ 或兼容发行版 | Hook、Controller、数据服务和控制台 |
| Python | 3.11 或更高 | Controller、Guidance、Hook 和状态服务 |
| Node.js | 20 LTS 或更高 | 构建或运行 Console；仅使用后端时可不安装 |
| npm | 随 Node 20 提供 | 安装前端依赖和生产构建 |
| PostgreSQL | 15+ | 生产 Bank 数据；需要 pgvector 时启用扩展 |
| SQLite | Python 内置 | Guidance Registry、任务状态和本地回执 |
| Git | 2.40+（可选） | 版本化配置、导出和升级回滚 |
| curl、tar、gzip | 系统工具 | 安装脚本、健康检查和发行包操作 |

Windows 可以运行 API 和 Controller，但 Codex/Hermes/Claude Code 的 Hook 路径、
权限模型和桌面端能力需要单独适配；本发行包的三宿主验收基线是 macOS/Linux。

### 7.2 依赖分层

EP 不要求每个使用者安装所有组件：

```text
最小入口层：Python + SQLite + MCP stdio
  → 说明书、L0、Get Preference、catalog、审计

历史证据层：PostgreSQL/pgvector + Controller/Data Plane
  → Facts、Experiences、Entities、recall、research、read_source

控制台层：Node.js + npm + Next.js build
  → 链路页、Bank 视图、回执和运行状态

宿主层：Codex / Hermes / Claude Code 的 Hook 或 MCP 配置
  → 把 EP 送入实际 Agent 回合
```

只需要偏好和目录时，可以先启用最小入口层；需要历史 recall/research 时，再启动
数据服务；需要可视化页面时，再安装 Node 和 Console 依赖。

### 7.3 Python 安装

推荐使用虚拟环境，避免污染系统 Python：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ./api
```

开发/测试依赖应安装到开发环境，不要把虚拟环境目录打进发行包：

```bash
python -m pip install pytest pytest-asyncio ruff
```

如果只运行 Controller、Guidance 和 Hook，可按对应目录的导入需求安装最小依赖；
发行者应在目标系统中运行 `python -m compileall` 和 `scripts/verify-package.sh`。

### 7.4 PostgreSQL 与 pgvector

生产使用建议：

1. 创建独立数据库和专用数据库用户；
2. 为生产、测试和演示分别使用不同数据库或不同 Bank；
3. 启用 pgvector，并验证向量维度与当前 embedding 模型一致；
4. 配置定期备份、恢复演练和 SHA-256 清单；
5. 数据库连接串只进入本机环境变量，不进入 README、Bank 或日志。

示例环境变量（值必须由使用者自行填写）：

```env
EVOLVING_PROFILE_API_DATABASE_URL=postgresql://user:password@127.0.0.1:5432/ep
EVOLVING_PROFILE_API_HOST=127.0.0.1
EVOLVING_PROFILE_API_PORT=8888
```

没有 PostgreSQL 时可以先运行目录和偏好入口，但完整历史检索、图谱和大规模来源
读取不可视为已通过。

### 7.5 服务、端口与健康检查

常见本地端口约定如下；部署时可以通过配置改动，但必须在宿主配置和 README 中保持
一致：

| 服务 | 默认端口 | 作用 | 健康检查 |
|---|---:|---|---|
| EP API / Data Plane | 8888 | Bank、来源和基础 API | `/health` |
| EP Controller | 12079 | recall、research、权限和路由 | Controller health endpoint |
| EP Source Reader | 12088 | 按 memory/chunk/document 回读来源 | Source API health |
| EP Console | 9999 | 链路页、Bank 页面和运行状态 | 浏览器打开 Console |

启动顺序建议：

```text
数据库 / Data Plane
  → Controller / Source Reader
  → MCP stdio server
  → Host Hook
  → Console（可选）
```

排障时不要只看“进程存在”：必须同时检查端口、健康端点、MCP `tools/list`、真实
工具调用和页面回执。

### 7.6 模型提供商与 Key

```env
EVOLVING_PROFILE_API_LLM_PROVIDER=openai
EVOLVING_PROFILE_API_LLM_MODEL=
EVOLVING_PROFILE_API_LLM_API_KEY=
EVOLVING_PROFILE_API_LLM_BASE_URL=
```

可使用云端模型或本地 OpenAI-compatible endpoint。不同功能可能使用不同模型：

- 事实/经历抽取：结构化 JSON 输出稳定优先；
- Observation/Preference 整理：需要更强的长文本和条件归纳能力；
- Reflect/Mental Model：需要明确来源和边界；
- Embedding：必须固定模型和向量维度，换模型前要迁移或重建索引。

Key 生效后先做最小健康检查，再做一条虚构文本的 retain/recall 测试。严禁用真实
个人数据作为首次连通测试样本。

### 7.7 数据目录与备份

建议把运行数据和源码分开：

```text
源码目录        发行包和配置模板，可版本化
数据目录        PostgreSQL、SQLite、回执和临时 workspace，不进入 Git
备份目录        加密数据库备份、配置备份、回执清单和恢复记录
```

备份至少覆盖：

- 主 Bank 数据库；
- Guidance Registry；
- Bank/Guidance 配置；
- 宿主 Hook 和 MCP 配置（脱敏）；
- 关键审计回执；
- 版本和迁移记录。

恢复验收必须在临时端口和临时 Bank 中完成，确认 catalog、Get Preference、recall、
research、read_source 和宿主工具列表均能工作，再切换生产入口。

#### 7.7.1 macOS 本地备份设置

完整安装路径可使用本包提供的模板创建独立、本机的加密备份任务：

```bash
./scripts/install-backup-macos.sh
```

安装脚本只会写入当前运行用户的 `~/.evolving-profile` 和
`~/Library/LaunchAgents/com.evolving-profile.backup.plist`。它不会导入发行者的
Bank、数据库、配置、Keychain 项或云端文件。首次运行前，使用者必须自行准备
`~/.evolving-profile/profiles/evolving-profile-api.env` 中的本机数据库连接；没有
该文件时备份任务会明确失败，不会伪造成功回执。

安装后，在 Console 的“记忆库配置 → 运行配置 → 备份设置”中可以设置：专用本地
备份目录、每日/每周/每月计划及时间、保留天数、最大套数、数据库/加密配置/回执/
SHA-256 校验。每周必须选择星期，每月必须选择日期；保存后会同步更新 LaunchAgent
的实际运行模式，而不是只变更界面显示。云端镜像的保存策略和凭据独立管理，页面
仅记录其预期保留数量，不能用本地清理规则代替云端保留政策。

默认模板是每天 `03:25`、保留 14 天/最多 14 套。它只是可调整的起点，不代表
对任何数据规模的通用建议。配置文件模板位于
`config/backup-settings.example.json`；实际生效文件仅存在于用户自己的状态目录，
不应提交到 Git 或发送给他人。

### 7.8 宿主前置条件

- Codex：能够运行 UserPromptSubmit/相关 Hook，并允许连接本机 MCP stdio server；
- Hermes：启用对应 MCP/Hook 配置，确认网关和桌面端工具列表可见；
- Claude Code：启用本机 MCP server，确认 `get_preference`、`recall`、`research`
  和 `read_source` 出现在 `tools/list`；
- 所有宿主：不得把真实 API Key 写进对话、截图或仓库；必须用临时空 Bank 做冒烟测试。

### 7.9 最小、标准和完整安装路径

```text
最小：Python + Guidance Registry + MCP stdio
标准：最小路径 + Data Plane + Controller + 一个空 personal-memory Bank
完整：标准路径 + Console + 三宿主适配 + 备份/恢复和回归测试
```

Key 只从环境变量或本机未提交的 `.env` 读取，不能写入 Bank、README、日志、
回执或导出包。支持 OpenAI、Anthropic、Gemini、Qwen/DashScope、OpenAI-compatible
endpoint，以及本地 Ollama/LM Studio（具体能力取决于部署的 API）。

默认主 Bank：`personal-memory`。来源归档和专用 Agent Bank 可以另行创建：

```text
personal-memory       日常主个人 Bank
source-archive-*      只读来源归档
agent-role-*          专用 Agent 的受限 Bank
test-memory           回归测试 Bank
```

## 八、Codex / Hermes / Claude Code

三种宿主使用同一 EP Controller 和工具契约：说明书、L0、Get Preference、
catalog、recall、research、read_source。宿主自身只负责上下文和 MCP 承载；
权限仍必须由宿主与服务端配置共同执行。

## 九、隐私和发行包边界

发行包不得含个人姓名、对话、Bank 导出、session ID、memory ID、浏览器配置、
本机路径或真实 Key。先运行：

```bash
./scripts/check-no-secrets.sh
./scripts/verify-package.sh
```

脚本通过只是必要条件；发布前仍需人工检查自定义 Prompt、截图、fixture、数据库
导出和压缩包。

## 十、回归验收

在全新临时环境和空 Bank 中验证：入口说明与 L0 可送达；Get Preference 可返回
候选；catalog 可逐层导航；recall 可返回候选和来源定位；research 可分页；
read_source 可回读原文；空结果不会伪装成“没有记忆”；三个宿主都能看到
`get_preference`，旧别名仍可兼容；日志和回执不泄露 Key 或个人数据。

升级时先备份 Bank、Guidance registry、配置和回执，再在测试 Bank 中跑迁移、
工具列表、入口注入和回归问题集，不直接覆盖生产数据目录。

## 十一、概念百科与责任边界

这一章面向第一次接触 EP 的 Agent、开发者和运维人员。每个概念都说明它是什么、
不是什么、由谁产生、进入哪一层，以及如何验证。不要把不同概念仅因为名字相似就
合并处理。

### 11.1 Bank

Bank 是一个逻辑记忆空间，不是一个主题卡片，也不是一个单独的向量索引。它通常
包含原始文档、分块、Facts、Experiences、Observations、Entities、Relations、
时间字段、来源定位和状态字段。

EP 的个人部署建议只有一个日常主 Bank，例如 `personal-memory`，用主题目录把
高校、健康、Agent 工程、交互偏好等分开导航。来源归档 Bank 和专用 Agent Bank
可以存在，但要明确它们是归档或权限隔离，不要让每个主题都变成互相断开的主记忆。

Bank 的典型边界：

- Bank 隔离数据和权限，不自动证明其中的内容正确；
- Bank ID 是路由和访问边界，不是用户身份本身；
- 同一个 Bank 可以有很多主题、实体和事实类型；
- 删除、合并或迁移 Bank 前必须完成导出、哈希和恢复演练；
- 任何 Agent 是否能看到某 Bank，要由宿主和服务端权限共同决定。

### 11.2 Facts（事实）

事实是一个被来源支持的命题、状态、规则或约束，例如“某服务当前使用某端口”、
“某项目在某日期完成验收”“某实体有某个别名”。事实可以随新证据更新、替代或
失效，但旧版本仍可能作为历史记录保留。

事实至少应尽量带：

- 主体和对象；
- 命题或状态；
- 发生/有效时间与提及时间；
- 来源 document/chunk/memory ID；
- 当前状态（valid、invalidated、unknown 等）；
- 证据范围和冲突信息。

事实不是“检索分数高的文本”，也不是 Observation 或 Mental Model。当前页面显示
为“事实 / Facts”；内部旧 schema 的 `world` 仍用于兼容，不应在迁移时随意改列名。

### 11.3 Experiences（经历）

经历是事件性记录，关注“谁在什么场景做了什么、过程怎样、结果如何”。它可以是
用户经历、助手执行、Agent 工具调用、项目推进、故障排查、会议、文件交付或某个
系统的运行过程。

经历和事实的区别：

```text
事实：某项目在 9 月 20 日完成验收。
经历：某 Agent 在 9 月 20 日执行了验收，发现按钮错位，修复后重新检查通过。
```

经历应尽量关联 `subject`、`involving`、项目、时间、结果和来源。无法确认主体时
保留 unknown；不能把助手转述、测试 fixture 或单条相似文本强行归为用户亲身经历。

### 11.4 Entities & Relations（实体与关系）

Entity 是跨记录稳定识别的对象，例如人、学校、公司、项目、Agent、Bank、文件、
服务和模型。Relation 是实体之间带方向、时间、范围和来源的关系。

实体层解决三个问题：

1. 把标准名、别名、缩写和历史称呼归到同一个候选实体；
2. 防止同名对象被错误合并；
3. 让经历、事实、观察和来源可以通过同一对象串起来。

实体关联不是自动真理。一个实体候选至少应检查主体、关系、时间、来源和范围；
图谱连线只能提供检索线索，不能单独支撑结论。

### 11.5 Observations（观察）

Observation 是从多条事实或经历中归纳出的模式。它可以描述重复偏好、因果趋势、
风险、策略或某种稳定现象，但必须记录证据范围、适用范围和不确定性。

Observation 是多维度偏好的前置草稿，不是偏好本身：

```text
一次行为 → 不能直接成为偏好
多次相似经历 → 形成 Observation 候选
跨任务、跨来源重复且有边界 → Preference 候选
审阅、冲突检查、版本化 → Active Preference
```

观察生成不能把助手自己的建议当成用户偏好，也不能把一个项目的临时约束扩大成
所有任务的全局规则。

### 11.6 Multi-dimensional Preferences（多维度偏好）

多维度偏好是经过整理和审阅、可在特定条件下指导协作的规则。它可以覆盖：

- 沟通语气与中文表达；
- 技术解释深度和是否需要例子；
- 建议的排序、推荐度和反例；
- 复杂任务的目标、约束、交付物和验收；
- PPT/Word/网页等交付规范；
- 记忆权限、主体核验和证据优先级；
- 何时使用 recall、research、read_source；
- 特定 Agent 的读取范围。

每条偏好应包含：正文、适用条件、例外、行动影响、scope、来源、revision、审阅
状态和 validity。偏好永远低于当前用户 Prompt、当前权威材料、工具结果和权限，
不能单独授权执行删除、发送、付款或其他高风险动作。

### 11.7 Mental Models（融合心智模型）

Mental Model 是把多条观察、事实和经历组织成可解释框架的高层产物，例如“事实、
经历、观察、偏好、来源应该如何单向派生”。它适合帮助 Agent 理解系统规律，但不
能替代底层事实。

心智模型需要版本和来源；新的反例可以导致刷新或降级。模型章节进入 Get Preference
时只能作为框架参考，具体结论仍要由 recall/read_source 支持。

### 11.8 Sources / Documents / Chunks

Source 是最接近原始材料的证据层。Document 是完整来源，Chunk 是检索和分页单位，
memory ID 是可回读的记录身份。摘要、Observation 和 Preference 都可能丢失作者、
否定词或时间范围，因此关键结论必须通过 `read_source` 回读 chunk 或 document。

来源中的命令、建议或旧配置只是参考材料，不自动变成当前指令。来源角色标签也不
单独证明真实发言者身份；需要结合具体引文范围和来源证明。

### 11.9 Get Preference

Get Preference 是 EP 的偏好入口。它不是“读完整偏好数据库”，也不是把所有候选
交给 Agent。它根据当前任务、阶段、条件、例外、已加载版本和审阅状态，生成有界
候选包。

```text
入口 Prompt
  → 主题/条件筛选
  → 审阅状态与版本检查
  → 候选排序与去重
  → 注入摘要/核心条件
  → Agent 需要时 read_preference_unit
```

`get_preference` 是新公开工具名，`get_task_guidance` 是兼容别名。候选进入上下文
只证明 Agent 看到了它，不证明 Agent 采纳了它。

### 11.10 catalog_list / catalog_search / catalog_read

这三个工具是目录导航，不是事实回答：

- `catalog_list`：列出主题、覆盖、新鲜度和来源数量；
- `catalog_search`：按标题、实体、摘要和概览找候选主题；
- `catalog_read`：从 topic ID 读取 L1 主题、问题槽位、来源覆盖和 L2 memory ID。

目录未命中不代表 Bank 没有资料；目录摘要不代表全部正文；catalog_read 返回的
memory ID 仍需 recall 或 read_source 核验。

### 11.11 recall

Recall 适合单点或小范围历史缺口。Agent 负责组织完整 query、对象、时间和未解
问题；EP Controller 将查询交给 Bank 检索，返回候选预览、memory ID、时间、状态和
source locator。EP 不把 recall 结果自动当事实，也不保证底层只使用某一种排序方式。

Recall 的正确后续是：

```text
recall 返回候选
  → Agent 筛选直接相关项
  → 重要结论 read_source
  → 仍有多跳缺口时升级 research
```

### 11.12 research / read_research

Research 适合多主体、多项目、时间线、因果过程和关系闭包。它可以拆 facets、建立
短期 evidence workspace、返回 research ID，并通过 `read_research` 继续分页。分页
读完不代表 Bank 全库穷尽，只代表当前工作区的候选页已读完；问题仍有缺口时要换
分面、补查原话或 read_source。

### 11.13 Graph / Constellation

图谱由实体、关系、时间边、来源边和状态边构成。它主要被 Controller 和 research
用于候选扩展、实体消歧、时间线和关系闭包；Agent 不需要每轮读取整张图。图谱适合
回答“谁参与了什么项目”“两个事件如何关联”，但图谱边必须回指来源，不能单独证明
事实。

### 11.14 Memory Packet 与审计

Memory Packet 是当前回合的交付格式，不是新的原始记忆库。它可以包含筛选后的 Facts、
Experiences、Observations、Preferences、来源时间、状态、证据 ID 和 coverage。

审计至少区分：

```text
发现候选 → 准入 → 渲染 → 传输 → 宿主可见 → Agent 是否使用（通常未知）
```

这可以解释“Bank 有记录但本轮没注入”“工具返回了但宿主未确认”“看到了但无法证明
最终采用”等不同状态。
