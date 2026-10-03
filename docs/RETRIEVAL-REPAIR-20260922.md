# EP 2.2 检索接入与送达修复记录

日期：2026-09-22。范围：Codex MCP 接入、Hook 候选送达、候选分页、自动探测边界和链路投影。

## 故障与修复

1. Codex MCP 注册指向不存在的旧 Python/脚本。已切换为当前 EP 启动脚本，保留配置备份。
2. 月度活动盘点没有匹配旧历史关键词，被判为 agent_decides，未探测。
   现使用独立历史计划；确定自足或用户禁止时跳过，未知不作为无记忆的结论。
   月度活动盘点建议直接 Research。系统探测只是补充线索，不替 Agent 判断证据覆盖。
3. 偏好回执计入了最终字符串裁剪掉的正文。现在只提供一份说明书，按完整条目装包，
   回执计数来自最终发出的条目。总入口字符预算为 12000，候选正文预算为 6500；
   条数上限仍默认 6，可在 Web 设置 1–20，实际返回还受预算与适用性约束。
4. 数量上限与字符预算同时生效时，游标覆盖了首个未读位置，12 条只能读到 8 条。
   现保留最早未读位置；deferred 仅携带定位，避免其正文绕过数量上限。
5. 原来的“500 token 窄探测”进入旧 Controller 后变成 mid/1200、两次查询。
   新 system_probe 直接执行一次低预算 Bank 请求，最多送出 3 条预览，最终输出按
   o200k_base 计数；编码器不可用时以 UTF-8 字节数作保守上界。失败不伪装为空结果。
6. 追问只取最近一句，丢失原始盘点目标。现保留同会话最多三条必要用户前文；
   当前用户权限限制独立检查，前文不继承执行授权。
7. 系统探测与 Agent MCP 调用分开投影。链路展示探测状态、请求数、送出条数及预算。
8. 说明书明确：read_source 的 source.text 才是原文；memory.text 是提取摘要。
9. 复杂盘点现在直接进入 Research 路由，Hook 不再做无范围的历史候选探测；窄 Recall
   只允许与当前主体短语重叠的候选进入上下文。Recall 为空、主体不匹配或范围不足时，
   路由回执明确要求升级 Research。
10. 实时审计类 Prompt（最新 Prompt、调用回执、链路问题）直接走 live_audit，跳过 Bank
    system_probe。页面把“同回合调用回执”和“Prompt 后时间窗观测”分开显示；后者不归因
    于当前 Prompt，但会显示 Recall、Research、read_source 和 find_sources 的调用数量。
11. MCP 活动账本对 read_source 记录 source_read_count 和有效原文返回数量，避免原文回读
    在页面上显示为零条。
12. 新增 codex://thread 审计判定：带线程 URI 且包含对话、回执、调用、问题核查等语义时，
    直接进入 live_audit，不查询普通历史 Bank。审计 Prompt 不再把 codex、threads、UUID
    等基础设施字符串当作实体候选。
13. 增加只读 `audit_thread_history` MCP 工具，统一读取 Codex 原始线程回放并返回用户消息、
    回合数、工具调用、失败数和时间覆盖。它明确标记 `source=codex_thread_history`，不把
    线程回放伪装成 Bank Recall/Research。
14. 复盘 2026-09-23 目标线程时发现，Hook 虽给出了 Recall 路由和空候选，Agent 仍可绕过 EP，
    用 `exec/rg` 搜索 `~/.codex/memories`。这类内部 system_probe 不计作 MCP Recall 回执。
    现对明确的偏好问题给出 `get_preference` 路由；时间限定的生成图片/素材盘点进入 Research。
    UserPromptSubmit 登记每回合必需的 EP 工具，PreToolUse 检测 Codex 原生 Memory 路径：只有
    用户本轮明确要求读取原生 Memory，或已成功执行对应 EP 工具后，才允许继续；缺路由、工具未
    调用或失败时会阻止静默替代并要求报告 EP 不可用。匹配器只在参数中出现真实绝对/主目录路径时
    拦截，单纯提到目录字符串或根目录示例不拦截。工具回执投影现在也识别 Get Preference。

## 2026-09-23 绕行修复复测

- 路由矩阵 10/10：个人格式偏好→Get Preference；上周生图盘点→Research；孩子/别名单点事实→Recall；自足/明确禁史→Skip；线程状态审计→live audit。
- Hook 级门控测试：未登记路由、未调用对应 EP 工具、调用了错误 EP 工具时，本地 Memory 访问被拒；对应工具成功后门控解除；用户明确要求查 Codex 原生 Memory 时允许访问。
- 回归套件：Host Adapter 102/102、Guidance 69/69、Status 28/28。
- 当前宿主直接 Get Preference MCP 调用成功，返回 2 条适用记录、无 deferred、无错误。
- 新启动 Codex CLI 的自然提问验收未完成：默认模型返回 `Selected model is at capacity`；临时指定的 `gpt-6-sol` 当前账户返回 404。两次均未出现 EP MCP 调用，因此不计为通过。
- 修改后的用户级 PreToolUse Hook 需要在 Codex `/hooks` 中审查并信任新定义；未完成该信任步骤的会话不会执行此 Hook。旧线程也不会自动刷新其启动时的 MCP 工具表。

## 验证证据

- Guidance 单测 69 项通过。
- Host Adapter 单测 104 项通过；包括候选范围门控、Research 升级提示、最终 stdout、预算、权限、Get Preference 路由、时间限定素材盘点、本地 Memory 绕行门控、误拦截反例及 UserPromptSubmit 到 PreToolUse 的回合绑定。
- Status 单测 28 项通过。
- Console 单测 122 项通过；TypeScript 和生产构建通过。
- 上述合计 298 项；旧“零自动读取”“不允许正文”等断言按已授权策略更换为实际送达、
  一次请求和用户权限边界的行为测试，没有靠放宽错误输出断言通过。
- 原问题真实数据服务 Hook 回放：
  - 输入：我最近一个月都干什么了，分几类。
  - recommended_route=research。
  - 回执 3 条偏好；最终 stdout 中可找到 3 条 ID 与正文。
  - 1 次自动请求，发现 7 条候选、送出 3 条预览。
  - 自动探测正文 314/500 token，未进入旧 Controller memory packet。
  - 入口 7986 字符，完整 Hook 输出 9023 字符。
- 默认 6 条上限启用的分页测试：12 条均可分页读取，不丢不重。
- Codex 原生 MCP 接入验收：get_preference 调用成功，memory_policy=forbidden，
  coverage=not_requested；未通过 shell 代调。
- Codex CLI 首轮自然提问验收：原样输入月度盘点问题，不指定工具名。
  已完成原生 research 1 次、read_research 4 次、read_source 7 次。
  7 次原文响应均含非空 source.text，分别为 2958、2879、2871、2879、578、2911、2947 字符。
  该运行在 180 秒验收预算处停止，未验收最终月度总结或整月覆盖完整性。
- Web 运行配置通过 Computer Use 检查并实际保存，回读仍为 6 条/500 token/自动探测开启。

## 验收边界

真实数据服务回放、独立 MCP 协议、Codex CLI 原生调用、既有桌面任务工具表分别记录。
当前修复回合尚未刷新出 EP 原生工具；Computer Use 禁止操作 Codex 自身应用，
因此既有桌面任务重载后的工具可见性仍待核验。不能将 CLI 验收写成桌面已刷新。
该次自然问题验证的是主动检索与原文送达，不是全套自然任务的答案质量基准。

## 复测入口

```sh
python3.11 eval/verify_retrieval_repair.py
python3.11 eval/verify_native_retrieval.py
```

第一项使用临时回执和 shadow_replay，读取真实 Bank，不执行 capture 或 retain。
第二项使用已有 retain-excluded canary 目录和 ephemeral Codex，会消耗一次真实模型调用。
测试原始事件只保存在本机临时目录，不应纳入公开发行包。

## 回滚

修改前副本：本机状态目录 backups/retrieval-repair-QrSQd7。
Console 已以独立 release 部署，上一 release 保留。
此次未删除 Bank、数据库或旧备份；未修改 Codex 原生长期记忆文件。

## Generalization Pass

The routing contract now uses task shape and evidence authority rather than a
small list of history keywords:

```text
current runtime / this-turn audit -> live receipts and thread events
current workspace material       -> files and page state
single historical fact           -> recall
multi-project, timeline, inventory -> research
load-bearing historical claim    -> read_source
self-contained material          -> skip
```

The system probe is a separate one-request candidate hint. It does not enter
the legacy Controller packet and does not claim coverage. Complex inventory
requests route directly to Research and receive no generic probe candidates;
Recall is the narrow route for a single historical fact. A narrow probe admits
only candidates with an exact current-entity overlap and declares Research as
the next route when its scope is empty or insufficient. The route receipt
carries required evidence slots such as `time_range`, `activities`,
`completion_state`, and `sources`.

Get Preference remains capped by a configurable page limit, but the limit is a
transport bound rather than a relevance target. The selector uses applicability,
conditions, exceptions, deduplication, and pagination. Source text is escaped
and whole candidate records are emitted; a receipt only counts items present in
the final output.

The flow projection distinguishes `system_probe_direct` from Agent MCP calls
and distinguishes both from a bounded post-Prompt time-window observation. It
can show task-shape route, dependency level, required evidence slots, probe
count, candidate admission/rejection, returned previews, and later
Research/read-source receipts without claiming that a candidate was used in
the answer.

When the native EP tools are missing from a host task, the fallback contract
is explicit: thread-list/thread-read evidence is labelled
`source=codex_thread_history`, with scanned/failed/uncovered ranges. It is not
reported as a Bank Recall or Research result. A missing-tool turn should first
attempt runtime guidance refresh and preserve the unavailable state if the
native tool surface does not appear. A direct read of `~/.codex/memories` is
now blocked for a history-required turn until the matching EP MCP call succeeds;
an empty bounded Hook probe is not treated as that call.
