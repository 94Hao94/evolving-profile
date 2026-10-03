# EP5.0 路由契约、命名统一与执行拓扑验收 PRD

**状态：** 执行基线
**适用版本：** EP5.0 运行态
**范围：** User Memory、Agent Process Memory、External RAG、Flow API、链路页、MCP/Hook 回执和发布一致性

## 1. 目标

本 PRD 将 EP5.0 中分散的路由命名、Agent Recall/Research 模式、候选送达回执、链路拓扑和箭头验收统一成一份可执行契约。

目标不是重建记忆库，而是保证：

1. 用户记忆和智能体过程记忆的命名统一；
2. Recall、Research、Preference、Agent Recall、Agent Research 的职责可区分；
3. 候选、返回、送达、原文回读和最终采用不混淆；
4. Hook、MCP、Controller、Flow API 和 Web 页面使用同一个 Prompt 绑定；
5. 最右侧汇聚箭头、回流箭头和分支箭头稳定显示；
6. 源码、编译发布目录和实际运行服务保持一致；
7. 升级后不再重复出现“已调用但页面不显示”或“页面有候选但实际未送达”。

## 2. 统一命名

### 2.1 User Memory

```text
User Recall              用户召回
User Research            用户研究
User Preference          用户偏好
User Scenario Summary    用户情景摘要
User Source Readback     用户原文回读
```

稳定键：

```text
user_recall
user_research
user_preference
user_scenario_summary
user_source_readback
```

### 2.2 Agent Process Memory

```text
Agent Recall             智能体召回
Agent Research           智能体研究
Agent Guidance           智能体指导
Agent Observe            智能体观察
Agent Writeback          智能体写回
Agent Evaluation         智能体评估
```

稳定键：

```text
agent_recall
agent_research
agent_guidance
agent_observe
agent_writeback
agent_evaluation
```

旧工具名继续兼容，例如 `recall`、`research`、`get_preference`、`search_agent_process_memory` 和 `agent_process_memory`。新回执必须同时记录：

```json
{
  "tool": "search_agent_process_memory",
  "canonical_route": "agent_recall",
  "display_name": "Agent Recall"
}
```

## 3. Agent Recall 与 Agent Research

### 3.1 Agent Recall

面向当前任务的低延迟过程经验检索：

```text
Prompt
 → 任务族/过程维度识别
 → 过程记忆候选
 → 模型、工具、环境兼容性门控
 → Guidance Packet
```

返回失败事件、修复模式、程序技能、过程观察、适用条件和反例。候选不能自动成为事实、全局偏好或永久 Skill。

### 3.2 Agent Research

面向过程图谱的多跳研究模式：

```text
Prompt
 → 多 Session/Project/Model/Tool 查询
 → Failure/Repair/Pattern/Skill 关系扩展
 → 时间、因果、冲突、反例和迁移分析
 → 研究结论与证据路径
```

适用于重复失败根因、跨项目比较、模型迁移、工具迁移、经验泛化和过程策略过期分析。它不能只是 Recall 失败后的机械重试，也不能直接晋升 Skill。

### 3.3 调用规则

```text
简单自足任务                    → 不调用
普通复杂执行任务                → Agent Recall
跨任务/跨项目/因果/迁移问题       → Agent Research
Recall 候选冲突或范围不足         → Agent Research
泛化、负迁移和能力趋势分析        → Agent Research
```

复杂问题可以直接进入 Agent Research，不强制先执行 Agent Recall。

## 4. 路由回执状态机

所有 User、Agent 和 RAG 路由必须记录：

```text
route_required
 → route_started
 → tool_called / hook_started
 → candidates_discovered
 → returned_to_host
 → delivery_state
 → source_readback
 → answer_use / unresolved
```

最低回执结构：

```json
{
  "schema": "evolving-profile.route-receipt.v1",
  "canonical_route": "agent_recall",
  "tool": "search_agent_process_memory",
  "prompt_id": "...",
  "session_id": "...",
  "turn_id": "...",
  "hook_invocation_id": "...",
  "required": true,
  "route_started": true,
  "candidate_count": 3,
  "returned_count": 3,
  "delivered_count": 3,
  "delivery_state": "delivered",
  "item_ids": ["..."],
  "source_scope": "prompt_bound",
  "unresolved": []
}
```

以下状态必须严格区分：

```text
not_required       未要求
not_observed       未观测到调用
returned_empty     已调用但返回 0 条
candidate_only     有候选但未返回宿主
returned           已返回宿主但未确认送达
delivered          已送达 Agent
readback           已完成原文回读
unavailable        服务不可用
```

## 5. Prompt 绑定与唯一真相源

所有回执必须使用 `prompt_id + session_id + turn_id + hook_invocation_id` 绑定。没有绑定的全局记录只能显示为“未关联活动”，不能归入当前 Prompt。

唯一真相源登记文件：

```text
config/route-registry.json
```

每条路由登记：

- canonical route；
- 兼容工具名；
- 显示名称和多语言；
- 所属泳道；
- 回执 Schema；
- Flow API；
- 候选、返回、送达字段；
- 详情卡字段；
- 失败态；
- 验收用例；
- 当前发布版本指纹。

文档规范：

```text
docs/EP5.0-ROUTE-CONTRACT-AND-TOPOLOGY-PRD.md
docs/EP-ROUTE-CONTRACT.md
tests/test_route_contract.py
docs/EP-RELEASE-CHECKLIST.md
```

旧 PRD 负责架构说明，本 PRD 负责路由和验收契约；出现冲突时，本 PRD 的回执和绑定规则优先。

## 6. 链路拓扑与箭头

### 6.1 结构要求

执行拓扑必须使用真实 Node/Edge 对象，不得使用字符箭头或背景装饰线模拟拓扑关系。节点固定保留，即使本轮未调用，也只能改变状态，不能从图中删除。

### 6.2 最右侧节点

以下节点必须分别拥有独立 Edge：

```text
User Memory Packet
Agent Process Packet
RAG Knowledge Packet
Context Assembly
User Writeback
Agent Writeback
Audit Receipt
Final Response
```

不得用一条共享背景线替代多个真实边。

### 6.3 箭头验收

每条边必须满足：

1. 有唯一 `edge_id`、`source`、`target` 和 `kind`；
2. 连接真实目标 Handle；
3. 箭头尖端落在目标节点边界内侧；
4. 线段、拐点、尖端使用一致状态颜色；
5. 缩放、刷新、滚动和重排后仍可见；
6. 最右侧汇聚边逐条检查；
7. 状态变化不删除结构边；
8. 点击边可以打开起点、终点、边类型和回执；
9. 视觉截图与 DOM/React Flow Edge 检查同时通过。

### 6.4 节点详情

每个检索或过程节点点击后必须显示：

```text
候选数
返回数
送达数
正文回读数
具体条目 ID
条目摘要
来源 ID
来源范围
关联工具/Hook
```

“送达 3 条”不能替代具体条目列表；没有绑定回执时必须显示“本轮没有绑定回执”，不能显示为 0 条。

## 7. 候选投影与过程记忆安全

Hook 自动注入必须生成 `evolving_profile_agent_process` 回执并绑定当前 Prompt。为兼容旧 Flow API 保存的投影记录必须标记 `route_receipt`，并从 Agent Process Memory 检索中排除，避免审计记录反向污染记忆。

过程候选不得和 User Facts、Experiences、Entities、Preferences 或 Scenario Summary 自动合并。图谱边只能作为导航和关系线索，不能单独升级为事实。

## 8. 发布一致性

源码、编译产物和实际运行服务必须进行版本指纹核对：

```text
source_revision
build_revision
runtime_revision
```

只修改源码而没有更新 9999/10002 实际运行产物，视为发布失败。升级后必须重新验证 MCP/Hook 回执、Flow API、节点计数、详情条目、箭头、语言切换和旧链路回退。

## 9. 验收矩阵

### 路由

- User Recall、User Research、User Preference 可区分；
- Agent Recall、Agent Research 可区分；
- 简单任务不误触发；
- 复杂任务正确进入对应模式；
- 直接 Research 不强制先 Recall。

### 回执

- 真实调用有绑定回执；
- 候选、返回、送达数量一致；
- 详情卡逐条显示；
- 空结果与未调用不混淆；
- 未绑定记录不自动归入当前 Prompt。

### 拓扑

- 最右侧全部箭头可见；
- Fork/Merge、回流和汇聚边可见；
- 节点和边均可点击；
- 新旧链路对同一 Prompt 的计数和条目 ID一致；
- 视觉截图和 DOM Edge 检查通过。

### 发布

- 9999 实际运行版本与源码版本一致；
- 中英文切换不改变数据和计数；
- 全量回归和真实 Prompt 验收通过；
- 失败时可通过 feature flag 回退旧链路。

## 10. 实施顺序

1. 建立 `route-registry.json` 和回执 Schema；
2. 增加 User/Agent canonical route 别名；
3. 接入 Agent Research 的按需模式；
4. 统一 Hook、MCP、Controller、Flow API 的 Prompt 绑定；
5. 修复最右侧箭头、Edge marker 和汇聚边；
6. 对账节点计数与详情条目；
7. 做真实 Prompt、空结果、失败、未绑定、语言切换和部署版本验收；
8. 通过长任务 Skill 的独立验收门后，才切换为默认链路。
