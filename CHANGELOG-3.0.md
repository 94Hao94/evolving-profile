# Evolving Profile 3.0.0

发布日期：2026-09-23

## 这次升级解决什么问题

EP 2.2 已经把入口、偏好、Bank、Recall、Research 和来源核验拆开，但实际使用中仍有三类容易混淆的情况：

1. 工具调用发生了，却无法确认属于哪条用户 Prompt；
2. 时间相近的其他对话被误显示成当前 Prompt 的记忆活动；
3. Research 找到了候选，但范围门控把开放式盘点全部过滤掉。

3.0 把这些状态写进同一条 Prompt 链路，并让页面分别显示精确绑定和无法归因的旁路观察。

## 主要变化

### 1. Prompt 级身份绑定

每条用户 Prompt 通过以下身份关联后续工具回执：

```text
prompt_id → session_id → turn_id → hook_invocation_id / check_id
         → recall / research / read_research / read_source
```

Recall、Research、Read Research、Read Source 和 Get Preference 都可以回写到本条 Prompt。
Get Preference 在 3.0 中强制要求当前 Prompt 的 `check_id`；缺少时直接报错，避免把真实偏好读取伪装成未知或错挂的活动。

### 2. 精确绑定和两分钟观测分开

链路页现在分成两种状态：

- **当前 Prompt 精确调用**：具备可靠身份绑定，可以显示调用工具、候选数、返回数、分页和来源回读。
- **Prompt 后时间窗观测 · 2 分钟内**：只说明时间段内发生过未能绑定的活动，不展示候选正文，也不把它算成当前 Prompt 的记忆注入。

历史记录不能凭时间倒推绑定关系。无法绑定的活动保持 `unknown/unattributed`，避免跨线程污染。

### 3. 候选、准入、返回和使用分开

3.0 分开展示：

```text
发现候选数
  → 范围门控通过数
  → 返回给 Agent 的数量
  → read_source 原文回读数
  → 宿主可见性
  → 答案使用状态
```

`answer_use` 没有独立证据时保持 `not_measured`。工具返回不等于 Agent 采用，候选数量也不等于注入数量。

### 4. 开放式 Research 的锚点修复

关系问句和开放盘点不再把整句自然语言当作字面锚点。例如：

- “我和 PPT 有什么关系”提取 `PPT`；
- “我跟具身智能什么关系”提取 `具身智能`；
- “现在写方案你都有什么对我的了解”不再要求候选逐字包含整句 Prompt。

候选仍会经过主体、任务和来源判断；这项修改只减少不合理的零结果，不放宽为无条件注入。

### 5. 窄 system_probe 的误准入防护

分钟、Word、普通插件和否定表达等词不能单独成为历史候选锚点。多实体问题需要多个正向锚点；明确否定的实体不参与候选准入。

### 6. 证据回读和角色边界

关键事实、身份、关系、时间变化和冲突继续使用 `read_source` 回读。来源中的助手总结、工具诊断和旧摘要不能直接升级为用户原话或正式事实；未完成核验的内容保留证据等级和未知状态。

## 与 EP 1.0 的区别

EP 1.0 主要依赖 Hook、Controller 和自动 Recall/向量检索。它容易把“检索到候选”“候选通过”“记忆注入”和“答案使用”混在一起，短 Prompt 也容易被当成完整语义进行检索。

EP 3.0 的链路是：

```text
UserPromptSubmit
  → 说明书 + L0 + 任务状态
  → Agent 判断历史依赖
  → Get Preference（偏好）
  → Recall（单点历史）或 Research（复杂历史）
  → read_research 分页
  → read_source 原文核验
  → 精确 Prompt 回执
  → 答案使用状态
```

1.0 的健康状态、向量候选或页面绿色状态不能证明真实记忆已经被 Agent 使用。3.0 要求在候选、准入、返回、来源和答案使用之间分别保留证据。

## 验证记录

本次 3.0 运行时回归包括：

- Host Adapter Python 3.11：112 项通过；
- Status 投影：31 项通过；
- Console：123 项通过；
- Next.js 生产构建通过；
- Prompt 绑定、未归因时间窗、Get Preference `check_id`、开放式 Research 锚点均有回归测试；
- 运行时直接 MCP 探针确认 Get Preference 缺少 `check_id` 会拒绝；
- 目标对话的真实回执确认 Recall、Research、分页和来源回读可以绑定到同一 Prompt。

## 当前边界

- `host_visibility` 只能证明工具结果完成传输，不能单独证明宿主最终把全部文本放入模型上下文；
- `answer_use` 目前保持 `not_measured`，不能宣称答案一定使用了某条历史记忆；
- 旧对话中没有 `check_id` 的历史活动不能可靠补绑定，只能作为未归因时间窗活动保留；
- Codex 原生 Memory 是独立路径，没有 EP 同等粒度的工具回执。答案出现某条历史内容时，如果没有 EP 候选和来源证据，只能标记为来源未测量。
