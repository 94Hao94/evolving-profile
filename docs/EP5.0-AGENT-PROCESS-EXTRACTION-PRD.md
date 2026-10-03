# EP5.0 Agent Process Extraction PRD

## 1. 背景与问题

EP5.0 已经具备 Agent Process Memory 的检索、兼容性门控和提示包注入，但当前自动提炼主要依赖 MCP 工具轨迹捕获。普通 Codex 任务中“走弯路、失败、修复、再次验证、最终成功”的完整 Session 轨迹没有稳定进入过程记忆，因此历史候选很多，当前新任务的过程经验沉淀不足。

必须补齐：

```text
真实 Session 轨迹
 → 过程事件
 → Failure Episode
 → Repair Pattern
 → 可迁移过程策略
 → Agent Recall / Agent Research
```

## 2. 当前审计结论

当前过程库存在大量 `trace`、`process_observation`、`episode`、`pattern` 和 `skill`，说明数据模型和晋升函数可用；但 Stop/PostToolUse 没有把普通任务的完整执行轨迹稳定送入 `record_trajectory`，且 `retain.py` 主要负责用户 Bank retain，不能代替 Agent Process Memory 提炼。

链路审计回执 `route_receipt` 只能证明候选已显示/送达，不得被当作新的失败经验或 Skill。

## 3. 目标与非目标

### 目标

1. 普通 Codex 任务自动记录有限、可审计的 Agent 过程轨迹；
2. 自动识别失败、恢复和独立验证；
3. 自动生成 Failure Episode 和候选 Repair Pattern；
4. 只有经过独立验证和跨任务证据的模式才能晋升；
5. 新经验可被 Agent Recall 召回，复杂关系可被 Agent Research 分析；
6. 记录 Session、Project、Task、Model、Tool 和环境关联；
7. 过程记忆提炼不把用户原始事实、私密内容或完整思维链复制进去。

### 非目标

- 不保存完整思维链；
- 不把 Agent 自己说“完成了”作为验证；
- 不把每个普通 Prompt 都写成记忆；
- 不把 route receipt 当作过程经验；
- 不自动把单次失败晋升为 Skill；
- 不改变 User Memory 的 Facts、Experiences、Entities、Preferences 边界。

## 4. 采集架构

### 4.1 轨迹来源

```text
PostToolUse
  → 工具名称、成功/失败、耗时、退出码、资源类型

Stop
  → 当前 Session/Turn 的用户任务、助手交付状态、工具事件摘要

PreCompact
  → 长任务阶段、未解决问题、验证状态和上下文压缩边界
```

每条轨迹绑定：

```text
session_id
turn_id
project_id / cwd hash
task_id / task contract
model family/version
toolchain
```

### 4.2 只保存过程证据

轨迹只保留：

- 阶段：understand、plan、retrieve、act、observe、verify、recover、deliver、reflect；
- 工具和结果状态；
- 错误类型、退出码和失败签名；
- 重试和恢复动作；
- 测试、编译、渲染、浏览器检查等独立验证器；
- 最终结果状态；
- 来源定位和时间。

不保存隐藏思维链，不把完整 Prompt 或完整回答复制进过程记忆正文。

## 5. Episode 自动识别

### 5.1 失败信号

- 命令非零退出；
- 测试失败；
- 构建失败；
- 浏览器 page error / console error；
- HTTP 4xx/5xx；
- MCP 工具错误或超时；
- 用户明确指出“没有完成、显示不对、点击无反应”；
- 结果与验收标准不一致。

### 5.2 恢复信号

- 后续尝试使用不同路径；
- 修改代码或配置后重新执行；
- 重试成功；
- 回滚后通过；
- 视觉/结构/接口重新验证通过。

### 5.3 Episode 晋升条件

```text
失败信号
 + 后续修复动作
 + 独立验证成功
 + 同一 Session/Task 绑定
 → Failure Episode
```

没有独立验证时只能记录为 `trace` 或 `process_observation`，不能形成正式 Episode。

## 6. Pattern 与 Skill 晋升

```text
多个相关 Episode
 → 相同失败形状和修复关系
 → Repair Pattern candidate
 → 跨任务复现
 → replicated / verified
 → 可进入 Agent Recall
```

Skill 仍然不是默认终点。只有固定流程稳定、适用范围清晰、反例已记录并通过迁移评测时，
才允许晋升为 Skill。

## 7. Agent Recall / Agent Research 使用

### Agent Recall

当前任务召回相关过程经验，返回候选、适用条件、反例和验证检查。

### Agent Research

跨 Session、Project、Model、Tool、Failure、Repair、Pattern 和 Skill 研究重复失败、根因、
迁移和经验过期。只读，不自动写回或晋升。

## 8. 去重与安全

- `route_receipt=true` 的记录从过程检索中排除；
- 相同 Session/Turn/Tool 事件使用稳定指纹去重；
- 同一失败在同一重试链中只生成一个 Episode；
- 跨项目经验必须保留项目边界；
- Model/Tool/Environment 变化时触发再验证；
- 用户当前要求和项目约束优先于旧过程经验。

## 9. 验收标准

### 单元与夹具

- 失败命令 → 修复 → 测试通过生成 Episode；
- 只有失败没有验证不能晋升；
- route receipt 不进入召回；
- 同一事件重复投递不会重复写入；
- Session/Project 绑定正确。

### 真实任务

至少验证：

1. 网页/链路视觉修复；
2. 软件测试失败与修复；
3. 文档分页/渲染失败与修复；
4. RAG 或 MCP 故障恢复。

每组都必须能看到：

```text
轨迹 → Failure Episode → Pattern candidate → Agent Recall
```

## 10. 实施顺序

1. 增加 Stop/PostToolUse 过程轨迹适配器；
2. 建立事件指纹和 Session/Project 绑定；
3. 实现 Failure Episode 检测；
4. 接入独立验证器门；
5. 生成 Pattern candidate 并排除 route receipt；
6. 接入 Agent Recall/Agent Research；
7. 用四类真实任务回归；
8. 通过长任务 Skill 独立验收门后发布。
