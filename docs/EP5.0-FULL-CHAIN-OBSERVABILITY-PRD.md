# EP5.0 全链路观测器与智能体过程记忆联动 PRD

**状态：** 设计稿，待实施
**适用版本：** EP5.0 运行态（用户记忆与 Agent Process Memory 联动）  2026-10-01
**作者：** CCY / Evolving Profile

## 1. 文档目的

当前链路页主要展示用户记忆的入口、L0、Preference、Recall、Research 和回答路径，但没有完整展示：

- Agent Process Memory 的过程观察、检索、门控、注入和写回；
- 外部 RAG 的独立检索链路；
- Provider、Fallback、Embedding、Rerank、JEV 与上下文组装；
- 用户记忆、智能体过程记忆、外部资料之间的边界；
- 候选、已返回、已送达、已采用、已验证之间的区别。

本 PRD 将链路页定义为“全链路观测器”，不是新的记忆库，也不在打开页面时重新执行 Recall、Research、RAG 或模型调用。

## 2. 核心原则

### 2.1 唯一真相源

每个事实只能有一个权威来源，链路页只读取来源回执与投影：

| 数据 | 唯一真相源 |
|---|---|
| 用户事实、经历、实体、偏好 | EP 用户记忆源记录 |
| Scenario Summary | 情景摘要源记录及其版本 |
| Recall / Research / read_source | MCP/Controller 工具回执 |
| Agent 过程轨迹 | Agent Process Memory 原始轨迹 |
| Failure Episode / Repair Pattern | 过程记忆写回记录 |
| 外部 RAG 候选 | 外部 RAG 检索回执与来源文档 |
| Provider / Fallback / 模型调用 | LLM Request 与 Provider 回执 |
| 实际上下文送达 | Context Packet / Host Receipt |
| 最终验证 | 独立测试、工具回执或验证器证据 |

页面不得用推断补齐缺失回执。没有回执显示“未观测”或“未知”，不能显示“没有”。

### 2.2 三类数据严格分离

1. 用户记忆：用户是谁、用户经历、事实、实体和偏好。
2. 智能体过程记忆：Agent 如何执行、失败、修复、验证和迁移。
3. 外部资料 RAG：用户指定目录中的文档和外部证据。

三者可以通过显式 ID 建立关系，但不能因为相似文本、同一时间或同一项目名称自动合并。

### 2.3 候选不等于采用

任何页面都必须区分：

```text
发现候选 → 通过范围/兼容性门控 → 正文返回 → 实际送达 → Agent 采用 → 独立验证
```

候选被发现不能说明它进入上下文；送达不能说明 Agent 采用；采用不能说明内容正确。

## 3. 完整运行链路

```text
Prompt Ingress
  ↓
Host / Hook / MCP Binding
  ↓
Full Prompt + Task Contract
  ↓
Guidance / L0 Map / Get Preference
  ↓
┌──────────────────────┬────────────────────────┬──────────────────────┐
│ User Memory Plane    │ Agent Process Plane    │ External RAG Plane   │
│ Facts                │ Task Classification    │ Source Routing       │
│ Experiences          │ Process Observation   │ Collection           │
│ Entities             │ Trajectory            │ Lexical Retrieval    │
│ Preferences          │ Process Retrieval     │ Vector Retrieval     │
│ Scenario Summary     │ Compatibility Gate    │ Fusion / RRF          │
│ Recall               │ Maturity Gate         │ Rerank               │
│ Research             │ Hint Injection        │ JEV Review            │
│ Read Source          │ Execute / Verify      │ External Readback    │
│ Read Scenario        │ Process Writeback     │ RAG Packet           │
└──────────────────────┴────────────────────────┴──────────────────────┘
  ↓
Provider / Fallback / Model Calls
  ↓
Context Packet Assembly + Token Budget
  ↓
Actual Host Delivery
  ↓
Agent Tool Use / Answer
  ↓
Independent Verification
  ↓
User Memory Writeback + Agent Memory Writeback + Audit
```

## 4. 页面信息架构

链路页顶部保留 Prompt 选择器、时间、Host、Session、Project 和刷新入口。

主视图提供五个切换：

```text
全链路总览 | 用户记忆 | 智能体过程 | 外部 RAG | 模型与上下文
```

默认是“全链路总览”。切换只改变展示范围，不改变运行链路，也不触发新的检索。

### 4.1 全链路总览

采用泳道布局，固定显示以下七条泳道，任何模块关闭或本轮未使用也必须显示状态：

1. Prompt 与宿主入口；
2. 说明、L0 和任务导航；
3. 用户记忆；
4. 智能体过程记忆；
5. 外部 RAG；
6. Provider、模型与上下文组装；
7. Agent 执行、验证、写回与审计。

每条泳道默认显示摘要卡；点击卡片打开右侧详情抽屉或居中的详情卡片，不跳转页面、不丢失当前滚动位置。

### 4.2 节点视觉约定

颜色只表达状态，不表达记忆类型事实：

| 状态 | 颜色 | 含义 |
|---|---|---|
| 已观测 / 已验证 | 绿色 | 有明确回执或验证证据 |
| 候选 / 待门控 | 紫色 | 发现但还未送达或未采用 |
| 时间窗观测 | 琥珀色 | 观察到活动但未绑定当前 Prompt |
| 未请求 / 不适用 | 灰色 | 当前任务没有请求或模块不适用 |
| 空结果 | 蓝灰色 | 已调用但返回 0 条 |
| 失败 / 不可用 | 红色 | 有明确错误或服务不可用 |
| 未知 | 深灰色虚线 | 回执不足，不能推断 |

不得用“空白卡片”表示未知，也不得把“0 条”显示成“没有记忆”。

## 5. 七条泳道的详细设计

### 5.1 Prompt 与宿主入口

节点：

```text
Prompt Received
→ Host Identified
→ Hook Stage
→ MCP Binding
→ Full Prompt Built
→ Task Contract
```

详情必须包括：

- prompt_id、turn_id、session_id、project_id；
- Host、Agent、Model；
- Hook 阶段和时间；
- 当前 Prompt 是否完整送达；
- Full Prompt 是否由宿主确认；
- Task Contract 的目标、约束和完成条件；
- 绑定失败、超时或缺失原因。

### 5.2 说明与导航

节点：

```text
Guidance Entry
→ Get Preference
→ L0 Memory Map
→ L1 Catalog
→ L2 Source Route
→ Task Route Decision
```

必须显示：

- 说明版本和 SHA-256；
- 实际送达正文或仅保存生成记录；
- L0 主题数、L1 可搜索实体数、L2 实际读取数；
- 当前任务投影；
- Preference 候选数、deferred 数量和补读状态；
- 路由建议与路由实际执行是否一致。

### 5.3 用户记忆

节点：

```text
Facts / Experiences / Entities / Preferences
→ Recall or Research
→ Scenario Summary (optional)
→ Read Source
→ User Memory Packet
```

所有节点都要分别记录：调用状态、候选数、正文数、送达数、回读数和来源 ID。

### 5.4 智能体过程记忆

节点：

```text
Task Family
→ Phase Detection
→ Raw Trajectory
→ Process Observation
→ Process Retrieval
→ Model / Tool Compatibility
→ Maturity / Counterexample Gate
→ Intervention Level
→ Hint Packet Delivery
→ Execution / Verification
→ Episode / Pattern / Capability Writeback
```

干预等级：

```text
observe | hint | recommend | scaffold | guard
```

详情要显示：

- 任务族、阶段、模型、工具链；
- 原始轨迹是否记录；
- 失败事件、重试和恢复；
- 过程候选及其来源；
- 兼容性、成熟度、反例和降级原因；
- 实际注入 Token 和提示等级；
- 是否独立验证；
- 是否写回 Failure Episode、Repair Pattern、Capability Observation；
- 是否进入 Skill/过程策略候选，而不是直接晋升。

### 5.5 外部 RAG

节点：

```text
Source Routing
→ Collection / Directory
→ Lexical Retrieval
→ Vector Retrieval
→ Fusion
→ Rerank
→ JEV Review (optional)
→ External Readback
→ RAG Context Packet
```

EP 内部记忆与外部 RAG 必须有不同颜色、不同 source_type 和不同 Token 预算。即使两者并行，也不能在页面上合并成“总候选数”后隐藏来源。

### 5.6 Provider、模型与上下文

节点：

```text
Primary Provider
→ Provider Test / Request
→ Fallback Provider (if needed)
→ Embedding
→ Rerank
→ JEV
→ Packet Merge
→ Token Budget Gate
→ Host Delivery
```

必须显示：

- 实际使用的模型和 Provider；
- fallback 是否发生以及原因；
- Embedding、Rerank、JEV 是否真正调用；
- EP、Agent Process、RAG 三类 Token；
- 截断、预算拒绝和优先级；
- Context Packet 的组成和 SHA-256；
- 实际送达回执。

### 5.7 执行、验证和写回

节点：

```text
Agent Context Received
→ Tool Calls
→ Tool Results
→ Answer Draft
→ Independent Verification
→ User Memory Writeback
→ Agent Process Writeback
→ Audit Receipt
```

“Agent 自报完成”“工具成功”“测试通过”“记忆写回”“经验晋升”必须分别显示。

## 6. 统一回执与唯一关联键

所有泳道节点使用同一回执结构：

```json
{
  "trace_id": "...",
  "parent_trace_id": "...",
  "prompt_id": "...",
  "turn_id": "...",
  "session_id": "...",
  "project_id": "...",
  "lane": "agent_process",
  "stage": "injection",
  "status": "delivered",
  "started_at": "...",
  "finished_at": "...",
  "candidate_count": 3,
  "returned_count": 2,
  "delivered_count": 1,
  "token_count": 318,
  "source_type": "agent_process_memory",
  "source_ids": [],
  "evidence_ids": [],
  "error": null
}
```

页面只展示回执投影，不自行拼接事实。缺少 `trace_id` 或 `parent_trace_id` 的事件只能显示在“未关联活动”，不能强行并入当前链路。

## 7. 点击与弹卡交互

### 7.1 点击原则

- 所有节点、状态徽标、候选数量和来源 ID 都可点击；
- 点击打开详情卡或右侧抽屉，不跳转新页面；
- 关闭后保留当前泳道、筛选、滚动位置和展开状态；
- URL 保存当前 Prompt、泳道和节点，支持刷新和分享；
- 同一节点重复点击不重复请求；
- 详情正文分页或按需加载。

### 7.2 详情卡层级

第一层：状态摘要、时间、数量和来源。
第二层：回执字段、门控结果、Token 和关联 ID。
第三层：原始工具回执、原文片段或过程轨迹，必须明确“候选”“送达”“来源核验”标签。

### 7.3 不可展示的情况

没有正文快照时显示：

```text
当时未保存正文快照，不能用重新检索结果替代。
```

没有绑定 Prompt 时显示：

```text
活动已观测，但无法归属当前 Prompt；仅作审计记录。
```

## 8. 多语言要求

### 8.1 唯一语言真相源

UI 文案必须来自统一 message key 或受控动态翻译表，不允许组件自行维护第二套文案。

### 8.2 动态文案

静态文案、API 状态文案和模板拼接文案都必须通过当前 locale 生成。禁止：

- 只翻译标题而保留动态正文中文；
- 在模块级常量中提前执行翻译，导致 locale 尚未建立；
- 用“details”“unknown”之类无意义占位替代未翻译文本；
- 用整页是否含中文判断语言是否正确。

### 8.3 用户数据边界

用户 Prompt、记忆正文、候选正文、文档原文默认保留源语言。语言验收分成：

1. UI 静态文案；
2. UI 动态文案；
3. 用户和业务原始数据。

只有前两类必须跟随 UI locale。

## 9. 性能与数据安全

- 打开链路页只读已保存回执，不触发模型或检索；
- 首屏只加载节点摘要，详情按需读取；
- 原始轨迹、候选正文和长文档必须分页；
- 不在页面、URL 或日志显示 API Key；
- 过程记忆和用户记忆使用独立权限与 source_type；
- 任何外部发送、写回、发布或高风险动作显示实际执行回执；
- 失败、超时、未知和未关联不能默认为成功或 0 条。

## 10. 后端接口建议

增加聚合只读接口：

```text
GET /api/evolving-profile/flow/{prompt_id}
```

返回：

```json
{
  "trace_id": "...",
  "prompt": {},
  "lanes": [],
  "nodes": [],
  "edges": [],
  "delivery": {},
  "writeback": {},
  "coverage": {}
}
```

接口只聚合已经存在的回执，不重新查询或生成候选。所有节点必须有状态，即使状态为 `not_requested`、`not_applicable` 或 `unknown`。

## 11. 验收标准

### 功能验收

- 全链路总览显示七条泳道；
- 用户记忆、智能体过程记忆、外部 RAG、模型上下文和写回均可切换；
- 每个节点可打开详情卡；
- 候选、送达、采用、验证状态不混淆；
- 没有回执时显示未知或未观测；
- 从节点可跳转到源记录、智能体记忆记录或 RAG 文档；
- 刷新和深链接保留当前 Prompt、泳道和节点。

### 真相源验收

- 页面展示的数量与回执一致；
- 不能通过目录、候选或推断生成事实；
- 用户记忆和过程记忆不能因相似文本自动合并；
- 所有跨泳道关系有 `trace_id`、`parent_trace_id` 或明确关联 ID。

### 多语言验收

- English、简体中文、西班牙语至少检查一条完整链路；
- 静态 UI、动态 UI 都不得出现错误语言；
- 用户原始中文 Prompt 和记忆正文保留中文；
- 不允许出现未翻译的动态模板或无意义 `details` 占位。

### 性能验收

- 首屏不触发新的 Recall、Research、RAG 或模型调用；
- 详情按需加载；
- 大量候选和轨迹分页；
- 1000 个以上节点不会一次性渲染到 DOM；
- 回执聚合失败时页面仍显示结构和未知状态。

## 12. 实施阶段

1. 定义统一 `FlowReceipt`、`trace_id` 和 source_type；
2. 接入 Prompt、Guidance、User Memory 当前回执；
3. 接入 Agent Process Memory 回执；
4. 接入 External RAG、Provider、Fallback、Embedding、Rerank、JEV；
5. 建立 Context Packet 和实际送达回执；
6. 完成七泳道总览和详情卡；
7. 完成多语言动态文案审计；
8. 完成真实 Prompt、空结果、失败、未绑定、回退和大数据量验收；
9. 灰度发布并保留旧链路页回退入口。

## 13. 反过拟合和长期演进

- 泳道由稳定能力接口定义，不由当前页面或某个模型名称定义；
- 新模块通过 `lane`、`stage`、`source_type` 注册，不改旧节点语义；
- 任务特殊规则放在任务适配器，不写入全局 Skill；
- 过程记忆只有跨任务验证后才能形成可复用策略；
- 新模型、Provider 或 RAG 算法无需改变链路协议；
- 旧回执缺字段时显示未知，不用当前版本数据倒填历史；
- 所有新增节点必须同时补齐：状态、来源、绑定 ID、详情入口、多语言、失败态和验收用例。
