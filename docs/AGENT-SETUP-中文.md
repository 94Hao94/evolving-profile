# 直接复制给不同 Agent 的安装话

[English](AGENT-SETUP.md) · [后台与网页](DEPLOYMENT-中文.md) · [各宿主接入](HOST-SETUP-中文.md)

先选实际使用的入口，不只看模型品牌。提示词是授权按文档做本地安装，不会让缺失的
凭据、权限、宿主能力或自动记录验证凭空出现。
维护分支仍为 `release/5.1.0`，具体补丁读 VERSION。

## Codex 桌面端 / CLI

**一句话版：**从 https://github.com/ccygod/evolving-profile-2.2 安装 `release/5.1.0`，按其中部署和 Codex 接入指南拉起我这套后端与网页，
只注册一个 EP，并实际验证记忆调用及允许记录任务的自动捕获链路。

**完整可复制版：**

```text
在新目录安装 https://github.com/ccygod/evolving-profile-2.2 的 release/5.1.0 分支，
读取 VERSION 确认当前补丁；先读 README、docs/DEPLOYMENT-中文.md、
docs/HOST-SETUP-中文.md 和 api/README.md。
首次用 ./scripts/install-ep51.sh --mode local --no-launch 安装构建，不跳过依赖。
通过安全的本地凭据流程配置我自己的数据库、聊天和向量服务；不编造密钥，
不复制作者的 Bank、对话或 .env。按文档分别启动 API、QueryController 和生产 Console。
端口占用先查属于谁，不终止无关进程；默认走文档的 personal-memory，
其他 Bank 必须在各读取器和实际回执中核对一致。
打开 http://127.0.0.1:9999/zh-CN，若改端口则同步全部地址。
先检查并备份现有 Codex MCP/Hook，只合并一个目标 EP，保留无关配置；使用真实绝对路径。
按宿主要求审阅并信任 Hook，不绕过权限。实际检查服务健康、网页点击、原生工具列表，
再用当前 Prompt 的绑定完成一次真实 EP 查询。
若开启自动记录，用允许留存的自然任务验证入口、队列、提炼真正完成和网页回执；
只在一次有限范围验证后计划必要的自有 Worker，不扫描全部历史，不向生产库塞合成测试。
解释网页推荐设置，核对运行 API 真正读取哪份 Provider 配置。
分别报告构建、服务、MCP、Hook、捕获、提炼、送达的通过/失败/不可用/未测试，
不把 tools/list 当完整接入。保留现有配置数据；未经选择不开 RAG/JEV/云备份，
不公开端口、不取消安全保护、不擅自 GitHub 推送或创建 Release。
```

## Claude Code CLI（终端）

**一句话版：**从 https://github.com/ccygod/evolving-profile-2.2 安装 `release/5.1.0`，按其中部署和 Claude CLI 指南拉起本机后端与网页，用 `claude mcp add`
注册 stdio 工具并做真实读取，不把未经验证的自动记录说成已完成。

```text
在当前 Claude Code CLI 中，将 https://github.com/ccygod/evolving-profile-2.2
的 release/5.1.0 安装到新目录并读取 VERSION。
按 docs/DEPLOYMENT-中文.md 和 docs/HOST-SETUP-中文.md 的 Claude CLI 部分执行。
安装新依赖，安全配置我的数据库、聊天与向量服务，启动 API、QueryController、生产
Console 并打开本地网页。先检查现有 Claude MCP 的 scope 和服务，保留并备份原配置，
以真实绝对路径只注册一个 evolving_profile_controller stdio 服务。
核对本机 CLI help 和会话 /mcp，再用当前 Prompt 绑定、正确 Bank 做真实记忆读取。
不要把 Codex Hook 复制到 Claude 设置，也不要把 Codex 扫描器指向 Claude 对话树。
自动捕获在生命周期、来源、去重和回执实测前标未验证，不制造成功。
解释网页的主模型、fallback、模块、相关度与可选功能，核对后端实际加载保存的 profile。
风险判断、RAG、JEV、云备份保持可选；保留数据与配置，不停止无关服务、不公开端口，
不写合成记忆、不提炼全部历史。逐项说明通过、失败、不可用和未测试。
后台配置 Claude Code Provider 不等于当前 Claude 已完整接入 EP。
```

## Claude Code 桌面端（本地 Code 页）

**一句话版：**在本地 Code 会话从 https://github.com/ccygod/evolving-profile-2.2 安装 `release/5.1.0`，按桌面接入说明复用正确的 MCP 配置且不重复注册，
拉起后端与网页，并在这个桌面会话内验证实际工具。

```text
在新目录安装 https://github.com/ccygod/evolving-profile-2.2 的 release/5.1.0 分支，
先读 VERSION、docs/DEPLOYMENT-中文.md、docs/HOST-SETUP-中文.md。
确认当前是桌面 Code 页的 Local 会话，不是普通 Chat、云端、SSH 或 WSL。
安全构建配置我自己的后端，启动 API/Controller/生产 Console，检查健康并打开网页。
检查 CLI 用户级、项目级和 claude_desktop_config.json 的 MCP 来源，保留无关配置，
消除同名歧义后只保留一个权威 EP 入口。按文档使用真实绝对路径注册 stdio 适配器，
在这次 Code 会话里查工具并真实调用，不能用独立 CLI 列表代替桌面验证。
不导入 Codex 全套 Hook，不在来源/生命周期/回执验收前宣称 Claude 自动捕获成功。
解释网页配置及实际生效的 Provider 文件，保留数据与权限。
RAG、JEV、风险判断、云备份及全历史处理未经选择不开。
分别报告已构建、已运行、已连接和已测试；送达未知、宿主不支持都如实说明。
不为了远端会话能用而公开本机端口，不进行未请求的 GitHub 发布。
```

## Claude Desktop 普通 Chat

**一句话版：**按 https://github.com/ccygod/evolving-profile-2.2/blob/release/5.1.0/docs/HOST-SETUP-中文.md 连接我已运行的本地 MCP；没有终端和浏览器能力，
就不要声称已经部署了系统服务或自动记录全部聊天。

```text
按 https://github.com/ccygod/evolving-profile-2.2/blob/release/5.1.0/docs/HOST-SETUP-中文.md
帮助当前普通 Claude Desktop Chat 接入 EP。
先检查是否有已授权的终端/浏览器工具。没有就给出文档中独立 CLI/Code 的后端安装提示词，
待后端就绪再配置 Chat 本地 MCP，不声称自己已安装依赖。
对已运行的 API/Controller，找到实际 Desktop 配置，备份并合并一个 EP mcpServers 项，
用真实绝对路径，不把 $HOME 当成 JSON 自动展开变量；保留其他服务和密钥。
按需要刷新应用，查工具和日志，用当前绑定与正确 Bank 验证一次显式读取。
本包没有 .mcpb 安装扩展，不编造下载包。
连接成功不等于 Claude Code Hook、自动 Chat 捕获、历史导入或答案采纳已验证，
失败和未知均分开报告。
```

## Hermes 或其他支持 MCP 的 Agent

> 按 docs/DEPLOYMENT-中文.md 安装同一 EP 后端，检查本宿主当前 MCP 注册契约和权限，
> 确认可用才配置一个 stdio 入口。实际验证本宿主调用，不照搬 Codex/Claude 设置，
> 不编造命令，也不宣称已全自动捕获；说明不支持的生命周期/来源能力并保留现有配置。

## 交付时应看见什么

- 真实产品版本和提交、安装及状态目录、这套服务的实际地址。
- 数据库和模型连接结果，不暴露密钥。
- 后端、网页、实际宿主入口和配置 scope 的状态。
- 原生工具可见、真实返回内容/数量、原文回读、送达分别有证据；不是每个任务都强制调全部工具。
- 若开自动记录，要有允许记录的来源、去重、提炼完成和实际产出的维度；新用户历史为空不等于安装失败。
- 配置哪些真正生效、哪些尚不支持、如何只停止自己的进程、备份和回退位置。

诚实的部分完成，比没有真正接好却宣布“全完成”更有用。
