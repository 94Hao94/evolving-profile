# EP 5.0 执行拓扑图重构 PRD

状态：设计审计通过，待实现

版本：EP 5.0 Topology Canvas v1

日期：2026-10-01

## 1. 目标

将 EP 5.0 的链路页从当前“CSS 网格卡片投影”升级为真正的执行拓扑画布，使其在结构、分支、汇聚、箭头、泳道、节点选择和详情查看方面接近参考图 MemTrace Execution Topology，同时保持现有 EP 回执、历史检索、智能体过程记忆、外部 RAG、审计和多语言功能不变。

本 PRD 只改链路的可视化渲染层和交互层，不改变记忆数据、检索结果、工具调用协议或回执事实。

## 2. 审计结论

### 2.1 当前实现的问题

当前链路图主要由 HTML/CSS Grid、按钮和字符箭头组成。它可以表达卡片顺序，但不能稳定表达真正的图关系：

- 箭头不是边对象，无法表示真实的输入端口和输出端口；
- Fork、Merge 只是文字或伪元素，不是可选择的图节点；
- 并行泳道没有共享坐标系，跨泳道连线难以维护；
- 长文本、窄屏和不同语言会改变卡片尺寸，导致线路错位；
- 真实执行路径和标准可用路径不容易分层；
- 右侧详情、节点点击和边点击无法形成稳定的画布状态；
- 继续调整 CSS 只能改善局部间距，不能解决布局引擎缺少图结构的问题。

### 2.2 参考图真正依赖的能力

参考图并不是普通流程图，而是一个有向、分层、带分组的执行拓扑：

1. 上段是串行主干；
2. 中段是三条并行泳道；
3. 每条泳道有自己的分支与汇聚；
4. 主干与泳道之间有跨层连接；
5. 下段是执行输出和写回；
6. 选中节点后，右侧显示固定的回执详情；
7. 节点和连线有状态、来源、时间和验证信息。

因此，单纯更换配色或继续堆 CSS 不能达到目标。

### 2.3 引擎审计结论

建议采用：

```text
React Flow / XYFlow

ELK.js 分层布局

自定义正交边

自定义泳道、Fork、Merge、Packet 节点

固定的 Receipt Inspector / 弹层
```

当前项目已经依赖 Cytoscape 和 `cytoscape-fcose`，但不建议使用 Cytoscape 作为执行拓扑的主引擎：

- Cytoscape 更适合实体图、星座图和关系网络；
- `fcose` 是力导向布局，不能保证参考图需要的串行主干和三条固定泳道；
- 执行拓扑需要端口约束、正交折线和固定分层，而不是自由力导向；
- React Flow 与 React 组件、弹层、国际化和现有页面状态的结合成本更低。

结论：

```text
实体图 / 星座图：继续 Cytoscape
执行链路图：迁移到 React Flow / XYFlow + ELK.js
```

## 3. 功能不受影响的兼容边界

### 3.1 保留不变的内容

以下内容不得由前端图引擎重新推断：

- Prompt 列表和分页；
- EP Recall、Research、Get Preference、Scenario Summary、Read Source 的真实回执；
- 用户记忆和智能体过程记忆数据；
- 外部 RAG 的来源和检索状态；
- Token、候选、返回、送达和回读数量；
- Prompt、Session、Project、Bank 和来源 ID；
- 审计日志和唯一真相源；
- 中文、英文及其他语言的运行时文案。

图引擎只负责：

- 将统一拓扑数据布局为节点和边；
- 渲染节点、泳道、边、状态和选中效果；
- 处理缩放、拖动、选择、弹层和详情显示。

### 3.2 真实状态与标准结构分离

拓扑图必须同时支持两类信息，但不能混为一谈：

```text
标准结构：系统理论上有哪些路线、节点和能力
实际回执：本轮真实调用了哪些工具、返回了什么、是否送达
```

显示规则：

- 标准节点可以显示为灰色或低饱和度；
- 已执行节点显示实际状态和回执数量；
- 未调用节点不能显示为已完成；
- 返回 0 条与未调用必须分开；
- 服务不可用与本轮未观测必须分开；
- 没有 Prompt 绑定的智能体过程回执时显示 `unknown / 未观测`，不能按时间猜测归属。

## 4. 统一拓扑数据模型

新增渲染适配层 `TopologySpec`，不直接让组件读取多个旧接口：

```ts
type TopologySpec = {
  schema: "evolving-profile.topology.v1";
  promptId: string | null;
  sourceScope: string;
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  lanes: TopologyLane[];
  selectedNodeId?: string;
  selectedEdgeId?: string;
};

type TopologyNode = {
  id: string;
  lane: "serial" | "user_memory" | "agent_process" | "external_rag" | "writeback";
  kind: "stage" | "fork" | "merge" | "packet" | "tool" | "writeback" | "receipt";
  labelKey: string;
  descriptionKey: string;
  status: "observed" | "candidate_returned" | "delivered" | "verified" | "not_observed" | "unknown";
  optional?: boolean;
  receiptIds: string[];
  metrics: {
    candidates: number | null;
    returned: number | null;
    delivered: number | null;
    tokens: number | null;
  };
  sourceScope: string;
};

type TopologyEdge = {
  id: string;
  source: string;
  target: string;
  kind: "serial" | "branch" | "merge" | "context" | "writeback";
  status: "active" | "available" | "not_observed" | "blocked" | "unknown";
  receiptIds: string[];
};
```

所有节点文本通过稳定英文键和当前 locale 映射，不把中文或英文直接写进布局算法。用户 Prompt 和记忆正文保留原始语言，不参与界面文案翻译验收。

## 5. 目标拓扑结构

### 5.1 串行主干

```text
Prompt Ingress
  → Host / Hook Binding
  → Task Contract
  → FORK
  → Context Assembly
  → Agent Execution
```

### 5.2 用户记忆泳道

```text
L0 / Preference
  → FORK
    ├─ Recall
    ├─ Research
    ├─ Scenario Summary
    └─ Read Source
  → User Memory Packet
```

### 5.3 智能体过程记忆泳道

```text
Observe Trajectory
  → Process Retrieval
  → Compatibility / Maturity Gate
  → Hint / Recommend / Scaffold / Guard
  → Process Memory Packet
```

### 5.4 外部 RAG 泳道

```text
Source Routing
  → FORK
    ├─ Lexical
    └─ Vector
  → Fusion / RRF
  → Rerank
  → JEV Review（可选）
  → RAG Packet
```

### 5.5 写回主干

```text
User Writeback
  → Agent Writeback
  → Audit Receipt
  → MERGE
  → Final Response
```

## 6. 布局引擎设计

### 6.1 ELK 布局约束

ELK 使用 layered algorithm，布局约束必须固定：

- 根方向为从左到右；
- 串行主干位于顶部和底部；
- 三条并行泳道垂直排列；
- 每条泳道内部保持从左到右；
- Fork 节点位于分支开始处；
- Merge 节点位于分支结束处；
- Packet 节点是每条泳道的输出节点；
- Context Assembly 位于并行泳道之后；
- 写回链路位于图底部；
- 端口使用固定方向：入口为 west，出口为 east，上下跨泳道边使用 north/south。

### 6.2 不允许的布局行为

- 不使用随机或力导向布局作为默认执行拓扑布局；
- 不让节点因语言切换随机重排；
- 不让长 Prompt 正文改变拓扑节点位置；
- 不让一个泳道的文本高度推动其他泳道线路穿过节点；
- 不把未执行节点从图中删除，否则会误导用户认为该能力不存在；
- 不把实际路径和标准路径画成同一种高亮样式。

### 6.3 正交边

默认使用正交折线：

- 线路不穿过节点；
- 箭头落点位于目标节点边界之外；
- 分支线使用同一主干颜色；
- 汇聚线在 Merge 前保持可追踪；
- 跨泳道线使用垂直段 + 水平段；
- 移动窗口尺寸或切换语言后重新布局并复核，不依赖固定像素猜测。

## 7. 交互设计

### 7.1 节点点击

点击任意节点打开统一的 Receipt Details 卡片，包含：

- 节点名称；
- 所属泳道；
- 本轮状态；
- 证据范围；
- Prompt、Session、Project 和来源 ID；
- 候选、返回、送达、Token；
- 调用时间和完成时间；
- 关联回执；
- 没有回执时的明确原因。

### 7.2 边点击

点击边显示：

- 上游节点和下游节点；
- 边的语义：串行、分支、汇聚、上下文或写回；
- 实际状态；
- 关联工具调用；
- 是否有真实回执。

### 7.3 右侧详情与弹层

桌面宽度下使用固定右侧 Inspector，移动端使用弹层。两者共用同一个 `ReceiptDetails` 组件和同一数据源，不能维护两套状态解释。

用户此前要求详情统一使用卡片弹出，因此右侧 Inspector 可以作为宽屏快捷预览，但完整内容必须仍能通过点击弹出卡片查看。

## 8. 视觉规范

### 8.1 泳道

- User Memory：青绿色；
- Agent Process Memory：紫色或琥珀色；
- External RAG：蓝色；
- Serial Spine：浅蓝色；
- Writeback：绿色；
- Audit：金黄色；
- 未观测：低饱和灰色；
- 阻断或冲突：橙色/红色。

### 8.2 视觉验收指标

桌面 1440×900 和 1440×1200：

- 串行主干、三条泳道和写回主干全部首屏可见；
- 任意线路不穿过卡片；
- 箭头尖端清晰落在目标节点外侧；
- Fork、Merge 和 Packet 可识别；
- 节点文字不被裁剪；
- 右侧详情卡片不遮住主图；
- 标准链路和实际链路一眼可区分。

移动宽度 390px：

- 画布可以横向平移或缩放；
- 节点不重叠；
- 关键线路不消失；
- 点击节点仍能打开详情卡片；
- 不强行把复杂拓扑压缩成不可读的一列。

## 9. 性能和稳定性

- 初始布局只计算当前 Prompt 的拓扑，不加载全部历史图；
- ELK 布局计算超时时使用确定性的静态 fallback 坐标；
- 节点数量超过阈值时保持分组，不把所有过程记录展开成节点；
- 画布只负责渲染，回执查询仍由现有 API 完成；
- 选择节点不重新请求整页数据；
- 语言切换只重算文案和布局，不改变节点身份；
- 页面刷新后通过 Prompt ID 恢复当前节点和当前缩放状态。

## 10. 迁移方案

### 阶段一：数据适配

- 新增 `TopologySpec` 生成器；
- 将现有 flow receipt、flow projection、agent process receipt 和 RAG 状态转换成统一节点/边；
- 为每个节点保留真实来源和未知状态；
- 编写数据契约测试。

### 阶段二：新画布并行实现

- 安装并锁定 `@xyflow/react` 和 `elkjs` 版本；
- 新增 `ExecutionTopologyCanvas`；
- 暂时通过 feature flag 与旧拓扑并行；
- 不删除原有 API 和详情逻辑。

### 阶段三：交互和视觉验收

- 接入节点/边选择；
- 接入 Receipt Details；
- 接入中英文；
- 进行桌面、移动、长文本和空回执验收；
- 使用 Computer Use 点击所有类型节点和至少一条边。

### 阶段四：切换默认视图

- 新画布成为默认链路图；
- 旧链路保留为“传统详细回执链路”；
- 连续两个版本无回归后再考虑移除旧渲染器。

## 11. 功能回归门

以下任何一项失败，都不能宣称迁移完成：

1. Recall、Research、Get Preference 和 Scenario Summary 的实际回执数量与迁移前一致；
2. 空返回、未调用、服务不可用和未知状态仍可区分；
3. 智能体过程记忆没有绑定回执时不会被错误归因；
4. 点击节点和边都能查看对应详情；
5. 详情卡片显示同一份唯一真相源数据；
6. Prompt、Session、Project 和来源 ID 不丢失；
7. 中英文切换不会改变节点身份、边关系或实际状态；
8. 传统详细回执链路仍可展开；
9. API 失败时页面显示可解释的不可用状态，而不是空白；
10. 生产构建、Console 测试、Playwright 测试和 Computer Use 验收全部通过。

## 12. 风险与回滚

### 风险

- 新依赖增加包体积；
- ELK 布局在极端长文本或移动宽度下需要 fallback；
- 迁移期间新旧视图可能短暂并存；
- 如果数据适配层错误，图可能看起来正确但状态不正确。

### 回滚

- feature flag 关闭新画布即可恢复旧链路；
- 不回滚回执 API 和记忆数据；
- 保留新旧截图和状态对账结果；
- 回滚判断以功能回归门为准，不以视觉主观判断单独决定。

## 13. 最终审计结论

经过对参考图、当前 CSS 网格实现、已有 Cytoscape 依赖、EP 回执边界和历史视觉问题的复核，结论如下：

1. React Flow/XYFlow + ELK.js 能够提供接近参考图的固定分层、正交连线、分组泳道、Fork/Merge 和节点交互；
2. 现有 EP 后端和回执协议不需要重写，只需要增加 `TopologySpec` 适配层；
3. 真实回执和标准结构可以在同一画布中清晰区分，不会因为更换引擎而丢失 Recall、Research、RAG 或智能体过程记忆信息；
4. Cytoscape 继续用于实体图和星座图，避免一个引擎承担两类不同图形；
5. 只有在数据适配、功能回归和 Computer Use 视觉验收全部通过后，才允许将新画布设为默认；
6. 这是一项可控的渲染层迁移，不是记忆链路重构，因此可以在失败时安全回滚。

本 PRD 的核心判断不是“换一个库就自动变好”，而是：用适合有向执行拓扑的布局与连线引擎，配合统一数据适配层和独立验收门，才能同时得到参考图的视觉效果和 EP 的真实回执能力。

## 14. 最后一轮实现前审计补充

### 14.1 已锁定的本地技术版本

当前本地工作区已安装并通过依赖解析：

```text
@xyflow/react 12.12.0
elkjs 0.12.0
cytoscape 3.34.3
cytoscape-fcose 2.2.0
```

其中 Cytoscape 继续服务于实体图/星座图；React Flow 和 ELK.js 只服务于执行拓扑。该分工不能被合并成一个通用图组件，否则会重新引入布局语义混淆。

### 14.2 ELK 到 React Flow 的拐点适配

ELK 计算出的节点位置和边的 sections/bend points 必须经过显式适配，不能只把 ELK 的 `x/y` 写入 React Flow：

```text
ELK node.x / node.y
ELK edge.sections[].startPoint
ELK edge.sections[].bendPoints
ELK edge.sections[].endPoint
        ↓
TopologyEdgeGeometry
        ↓
CustomOrthogonalEdge
        ↓
React Flow SVG path
```

适配器必须保留 `edge.id`、`receiptIds`、`status` 和 `sourceScope`，几何转换不得覆盖业务回执字段。没有拐点时才允许使用最短直线 fallback。

### 14.3 布局失败和降级

ELK 是布局器，不是业务真相源。以下情况必须提供确定性降级：

- ELK 超时：使用预先定义的静态 TopologySpec 坐标；
- 节点尺寸无法测量：使用语言无关的最小尺寸，再重新布局；
- 某条边引用未知节点：保留边为 `unknown`，不让页面崩溃；
- 局部泳道布局失败：只降级该泳道，不影响其他泳道；
- API 无回执：继续显示标准结构，但所有真实状态为 `unknown/not_observed`。

降级状态必须在画布顶部显示，不能静默伪装成正常布局。

### 14.4 不混淆标准链路与实际链路

最终画布至少保留两套明确状态：

```text
standardGraph：完整能力结构
observedOverlay：当前 Prompt 的真实回执覆盖
```

标准图决定“节点在哪里”；实际回执决定“节点和边如何高亮”。这样即使本轮没有调用 Recall，Recall 节点仍然存在，但显示为未观测，而不是从图中消失。

### 14.5 实现完成的必要证据

在新拓扑设为默认前，必须同时具备：

1. `TopologySpec` 数据契约测试；
2. ELK 布局和拐点适配测试；
3. 空回执、返回 0 条、不可用和真实返回四种 fixture；
4. 中英文截图对比；
5. 1440px 桌面和 390px 移动端截图；
6. Computer Use 点击至少一个串行节点、一个泳道节点、一个分支节点、一个 Packet 和一条边；
7. 旧链路回滚开关验证；
8. 生产构建和全量测试通过。

### 14.6 审计结论

本 PRD 在设计层面已经闭合：引擎、数据适配、布局约束、交互、真实回执边界、国际化、性能、降级和回滚均已覆盖。剩余风险属于实现期风险，不能通过继续扩写 PRD 消除，必须由实现后的截图、Computer Use 和回归测试验证。

## 15. 现有回执详情功能不可回归契约

这是本次迁移的强制约束。新图引擎只能改变“怎么画”，不能改变“回执展示了什么”。

### 15.1 节点摘要必须保留

每个有回执或候选数据的节点仍必须在节点卡片上显示：

- 候选条数 `candidates`；
- 返回条数 `returned`；
- 送达条数 `delivered`；
- Token 数量 `tokens`（有数据时）；
- 当前状态：未观测、已调用、返回 0 条、已送达、不可用或未知。

这些数字必须来自现有唯一真相源的回执适配，不允许由图引擎重新估算，也不允许因为节点换成 React Flow 就只显示一个笼统的“已调用”。

### 15.2 点击节点必须能逐条查看送达内容

点击 Recall、Research、Get Preference、Scenario Summary、Read Source、智能体过程记忆、RAG、上下文包及写回节点时，详情卡片必须继续提供逐条回执：

```text
条目 ID / 来源 ID
条目类型
摘要或正文片段
候选状态
是否返回
是否送达 Agent
是否完成原文回读
来源范围
关联工具调用
```

“送达 6 条”只能作为摘要，不能替代“这 6 条具体是什么”。如果正文未送达，必须明确显示“候选已返回但正文未送达”；如果没有回执，必须显示“本轮没有绑定回执”，不能显示空白卡片。

### 15.3 数据适配要求

`TopologySpec` 节点不得只保存计数，必须同时保存完整详情引用：

```ts
type ReceiptProjection = {
  candidates: number | null;
  returned: number | null;
  delivered: number | null;
  tokens: number | null;
  itemIds: string[];
  items: ReceiptItem[];
  sourceScope: string;
  deliveryState: "not_observed" | "returned_empty" | "returned" | "delivered" | "unknown";
};
```

图节点只渲染 `ReceiptProjection`，不直接读取多个后端接口。这样更换布局引擎不会丢失送达明细，也不会出现节点数字与弹层明细不一致。

### 15.4 强制一致性验收

新画布切换默认前，必须验证：

1. 节点显示的候选数等于弹层回执中的候选数；
2. 节点显示的送达数等于弹层中 `delivered=true` 的条目数；
3. 弹层逐条内容的 ID 与现有旧链路详情一致；
4. Recall、Research、Preference、Scenario 和 RAG 至少各有一个真实或 fixture 回执样本；
5. 返回 0 条时弹层显示空结果原因，而不是空白；
6. 候选已返回但未送达时，节点和弹层都明确区分；
7. 没有 Prompt 绑定过程回执时，不得按时间或全局记录补配；
8. 旧链路展开视图与新画布对同一 Prompt 的计数和条目 ID 完全一致；
9. 中英文切换只改变文案，不改变条目、计数和来源；
10. 点击节点、点击分支节点、点击 Packet 和点击边后，详情均可打开且不会丢失逐条数据。

### 15.5 迁移安全策略

- 先保留现有详情数据适配器，再接入新画布；
- 不允许直接把旧组件中的 `items` 降级成 `count`；
- 新旧画布并行期间进行同 Prompt 双渲染对账；
- 任何计数或送达明细不一致，feature flag 自动回退旧画布；
- 只有连续回归通过后，才允许新画布成为默认视图。
