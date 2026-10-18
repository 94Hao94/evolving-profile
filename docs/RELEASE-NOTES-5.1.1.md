# Evolving Profile 5.1.1 — Deployment and host onboarding

日期：2026-10-17。状态：贡献分支补丁；实际提交和 PR 状态以
[发布记录](RELEASE-LEDGER.md)为准，不移动旧 RC 标签，不自动创建 GitHub Release。

## 解决的问题

旧说明把基础构建、后台运行、工具注册和自动记录放在相近段落，新用户容易把
“构建成功”理解成“完整部署”。Claude Code CLI、桌面 Code 与普通 Chat 也没有分开。
本补丁把这些阶段拆成可执行、可核对的步骤，不增加未经验证的宿主能力承诺。

## 本次变更

- 2026-10-18 指导工具参数防护：共享任务绑定先校验对象/字段类型，运行恢复工具
  严格检查单个 `runtime_event.failure`。错误参数返回可纠正的字段提示，不再抛出
  `'str' object has no attribute 'items'`，也不通过猜测转换错误事件或递归补查掩盖问题。
  stdio 回归覆盖错误调用后在同一进程中正确重试；不改检索阈值、记忆数据或密钥。
- 中英文 README 末尾明确 EP 基于 Hindsight 开发，NOTICE 同步说明上游基础和贡献边界。

- 后续链路图修复：保存实际 Chrome 校准的39个可见节点/标签，底图、动态框与字号
  使用同一坐标空间；布局写入安装级共享文件，带修订号冲突保护、原子保存和前版备份。
  浏览器旧草稿保留，缓存不是写入权威。语言切换失败回退也不会把中文覆盖项写进英文。
- 中英文 README 强化五维偏好与融合心智模型亮点，新增完整记忆能力说明；
  新链路实拍不显示私人 Prompt 栏，不把未知送达或历史候选数包装成准确率。

- 中英文完整[部署指南](DEPLOYMENT-中文.md)：环境、自己的凭据、默认 Bank、
  Guidance 初始化、API/Controller/生产网页、健康检查、Worker 与配置生效位置。
- 中英文[宿主接入](HOST-SETUP-中文.md)：Codex MCP/Hook 审查与信任；Claude CLI
  命令、桌面本地 Code 配置优先级、普通 Chat JSON，分开给出边界与验收。
- 中英文[Agent 提示词](AGENT-SETUP-中文.md)：每个入口一句话与长版步骤，要求真实
  工具、来源、送达和写入证据；Hermes 不编造专用注册命令或自动捕获能力。
- 新装 Controller 合约/访问策略示例，不启用实验 memory-OS 或私人历史快照。
- `VERSION` 是产品补丁唯一权威；release manifest 的投影不一致或格式错误将被预检拒绝。
  Console 包版本与本补丁同步；API/SDK/适配器的独立组件版本不全局替换。

## Upgrade / migration / rollback

This is a documentation, example-configuration and release-preflight patch, not
a database migration or an automatic rewrite of installed host settings. Preserve
existing `.env`, Bank, Guidance registry, queues, hooks and owned service profiles.
Do not replace an existing Controller contract with the new-install minimal one.
Review source/dependency/build compatibility before adopting updated Console
metadata. Roll back the matching source/build set, not old data over new writes.

The contribution branch remains `release/5.1.0` to continue PR4; it now carries
the patch from VERSION. Old RC1/RC2 downloads remain old. No stable/new Release
is implied by a branch push.

## Known limits / 已知边界

- Installer remains build-only; system dependencies, credentials, service start,
  MCP registration and reviewed automation are separate actions.
- Claude recipes use current official formats; they do not certify a live
  Claude CLI/desktop end-to-end lifecycle. No `.mcpb` package or automatic Chat
  capture is added. Codex remains the most exercised host.
- The stdio adapter's default Bank is still fixed. Custom Bank and alternate
  state roots require alignment and actual receipt checks, not a lone env edit.
- Manual API `.env` and web-generated Provider profile are separate unless
  explicitly connected. Save success is not proof of effective backend reload.
- [Existing dependency risks](DEPENDENCY-RISKS.md) remain disclosed; this patch
  does not fix or hide them, claim all-history quality, or relax source checks.

## Verification

Tests, example startup, Markdown/render/link checks and independent fresh-reader
review are recorded for the actual published commit in [release ledger](RELEASE-LEDGER.md).
An isolated Controller/MCP probe does not prove native Claude delivery. No
production credentials or private history are needed for documentation checks.

## 作者与致谢

EP 发行维护者 CCY；保留 [NOTICE](../NOTICE.md) 和现有上游许可与致谢。
个人仓库与朋友仓库的贡献 PR 是同一发行线的两个渠道，不是两套独立实现。
