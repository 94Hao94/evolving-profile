# 宿主接入：Codex、Claude Code 与 Claude Desktop

[English](HOST-SETUP.md) · [先启动后端](DEPLOYMENT-中文.md) · [给 Agent 的提示词](AGENT-SETUP-中文.md)

## 先说明验证程度

Codex 是 EP 当前验证较充分的宿主。公开 Python 适配器能够隔离初始化并列出用户/智能体
工具，但这不代表已在新装 Claude 中验证生命周期、自动捕获、来源解析和上下文送达。
下方 Claude 命令采用官方格式，真实端到端验收仍要在目标安装上记录。
本包没有 `.mcpb` 安装扩展，也没有统一的全宿主一键部署器。

先按[部署指南](DEPLOYMENT-中文.md)准备默认 `personal-memory` 和后台。
以下使用 API8888、Controller12079；改端口时同步全部地址。
只注册**一个** EP 控制器，不要同时保留当前名和旧 `hindsight_controller` 别名。

## 1. Codex 桌面端 / CLI：注册 MCP

先执行 `codex mcp list`。已有 EP 时用
`codex mcp get evolving_profile_controller` 检查并备份，不能盲目重复添加或覆盖。
新安装在源码根目录执行：

```bash
EP_DIR="$(pwd -P)"
codex mcp add evolving_profile_controller \
  --env EVOLVING_PROFILE_CONTROLLER_URL=http://127.0.0.1:12079 \
  --env EVOLVING_PROFILE_SOURCE_API_URL=http://127.0.0.1:8888 \
  --env EVOLVING_PROFILE_GUIDANCE_SRC="$EP_DIR/guidance" \
  --env EVOLVING_PROFILE_GUIDANCE_CONFIG="$HOME/.evolving-profile/guidance-v1/guidance-v1.json" \
  -- "$EP_DIR/api/.venv/bin/python" "$EP_DIR/host-adapter/evolving_profile_controller_mcp.py"
codex mcp list
```

依赖必须先装好；图形应用不一定继承终端 PATH，所以注册实际的 Python/脚本绝对路径。
Codex MCP 通常存于 `~/.codex/config.toml`，项目层和受管策略也可能影响可见性。
在桌面端检查实际 MCP 列表；工具目录没有刷新时再开新会话，不要反复重启 API 碰运气。

核对工具中有 `memory_check`、`user_preference`、`user_recall`、`user_research`、
`agent_recall`、`agent_research`、`search_scenario_summary`、`read_scenario_summary`、`read_source`。
需要新绑定时为当前原始 Prompt 调用 `memory_check`，只在该 Prompt 使用返回的 check ID；
不编造、不沿用上轮 ID。新库返回空可以正常，不能编出命中证明安装成功。

## 2. Codex 自动记录：单独配置和信任 Hook

MCP 注册不会安装 Hook。先备份 `~/.codex/hooks.json`、项目 Hook 和 `config.toml`
中的 inline Hook；Codex 会合并来源，重复注册可能重复捕获。保留无关处理器，同一层
优先用一种表示方式。

新安装用本地编辑器创建自己的 `~/.evolving-profile/codex.json`；已有文件要合并而非覆盖：

```json
{
  "evolvingProfileApiUrl": "http://127.0.0.1:12079",
  "bankId": "personal-memory",
  "agentName": "codex",
  "autoRecall": true,
  "autoRetain": true,
  "retainTokenThreshold": 12000,
  "retainTailMinAgeSeconds": 1800
}
```

Hook 和留存调度器共用同一配置/队列，只记录允许留存的任务。
下面是**绝对路径模板**：先将所有 `/absolute/ep` 替换成实际安装目录，检查文件存在，
再合并事件组。不能原样安装，更不能整文件覆盖用户其他 Hook：

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "\"/absolute/ep/api/.venv/bin/python\" \"/absolute/ep/host-adapter/session_start.py\"", "timeout": 15}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "\"/absolute/ep/api/.venv/bin/python\" \"/absolute/ep/host-adapter/recall.py\"", "timeout": 30}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "\"/absolute/ep/api/.venv/bin/python\" \"/absolute/ep/host-adapter/post_tool_use.py\"", "timeout": 15}]}],
    "PreCompact": [{"hooks": [{"type": "command", "command": "\"/absolute/ep/api/.venv/bin/python\" \"/absolute/ep/host-adapter/pre_compact.py\"", "timeout": 10}]}],
    "Stop": [{"hooks": [{"type": "command", "command": "\"/absolute/ep/api/.venv/bin/python\" \"/absolute/ep/host-adapter/retain.py\"", "timeout": 45}]}]
  }
}
```

Guidance 使用部署指南生成的用户目录绝对配置。改位置时通过经过审查的启动 wrapper
设置环境，不能假定图形应用继承任意 shell export。
在 Codex `/hooks` 或相应宿主入口审阅并信任具体定义；更新哈希后可能要再次信任。
不绕过此流程，不因为源码有 `PreToolUse` 拒绝门或专项 canary 就全装进去。

先验收自然 Prompt 的入口、上下文输出和来源身份，再验收允许留存的 Stop 捕获与提炼完成。
token 阈值和尾批年龄会使小批次延迟提交，捕获不等于马上入库；使用队列就需要
[留存调度](DEPLOYMENT-中文.md#6-自动记录提炼和后台任务)。压缩检查点是恢复导航，
不等于整个 Session 已有完整情景摘要。

## 3. Claude Code CLI：先接显式工具

先查本机 `claude --version`、`claude mcp add --help`、`claude mcp list`，
不为了检查语法额外调用模型。新建用户级注册，在 EP 根目录执行：

```bash
EP_DIR="$(pwd -P)"
claude mcp add \
  --env EVOLVING_PROFILE_CONTROLLER_URL=http://127.0.0.1:12079 \
  --env EVOLVING_PROFILE_SOURCE_API_URL=http://127.0.0.1:8888 \
  --env EVOLVING_PROFILE_GUIDANCE_SRC="$EP_DIR/guidance" \
  --env EVOLVING_PROFILE_GUIDANCE_CONFIG="$HOME/.evolving-profile/guidance-v1/guidance-v1.json" \
  --transport stdio --scope user evolving_profile_controller \
  -- "$EP_DIR/api/.venv/bin/python" "$EP_DIR/host-adapter/evolving_profile_controller_mcp.py"
claude mcp list
```

把 `--transport`、`--scope` 放在环境参数与服务名之间，避免服务名被 `--env` 当成变量值。
本机 CLI 语法若不同，以其 help 为准，保持同样的可执行文件、参数与环境；不把模型密钥
写进 shell 历史。在会话 `/mcp` 看实际连接和工具，再进行带当前绑定的真实范围查询。
项目级可用官方 `.mcp.json` 并走批准流程，但不要提交本机绝对路径或密钥到共享项目。

**这条路线不会开启 Claude 自动捕获。** Claude Code 支持同名 Hook 事件，不代表 EP 的
Codex transcript、turn ID、来源资格和队列就天然兼容。不要把 Codex 全套 Hook 直接复制到
`~/.claude/settings.json`。专项桥接要实测自然任务的来源解析、隔离、去重和回执。
未完成前，显式查询只在实测通过后标可用，自动捕获标未验证。
EP 后台使用 Claude Code Provider，是另一项功能，不是 Claude 宿主适配证明。

## 4. Claude Code 桌面端：本地 Code 页面

选择 **Code → Local** 和正确的本机项目。官方当前支持复用 CLI 的 `.mcp.json`、
用户级 MCP 和相应 Hook。可用上面的 CLI 命令，或在桌面连接器/设置中配置等价入口；
还要在桌面这次会话里查实际工具，不能用终端列表代替。

当前桌面本地 Code 也会加载 `claude_desktop_config.json` 的服务。同名重复配置可能优先
采用它而非 CLI/项目定义；先核对所有来源，选一个权威入口。
独立 CLI 不会自动读取普通 Chat 的这个文件。以官方当前规则为准，不泛化为所有版本一致。

云端或 SSH 会话的 `127.0.0.1` 是远端，不一定是你的笔记本。本机 Python 路径和 EP
端口不能直接照搬过去。本文不认证云端、SSH、WSL，不以公开端口作为省事解决办法。
Claude 自动记录的边界与 CLI 相同。

## 5. Claude Desktop 普通 Chat

通过桌面应用的 Developer/本地 MCP 设置找到实际 `claude_desktop_config.json`。
macOS 通常在 `~/Library/Application Support/Claude/` 下；先备份再合并一个
`mcpServers` 项，保留无关服务。下面绝对路径都要替换，JSON 内的 `$HOME` 不会自动展开：

```json
{
  "mcpServers": {
    "evolving_profile_controller": {
      "command": "/absolute/ep/api/.venv/bin/python",
      "args": ["/absolute/ep/host-adapter/evolving_profile_controller_mcp.py"],
      "env": {
        "EVOLVING_PROFILE_CONTROLLER_URL": "http://127.0.0.1:12079",
        "EVOLVING_PROFILE_SOURCE_API_URL": "http://127.0.0.1:8888",
        "EVOLVING_PROFILE_GUIDANCE_SRC": "/absolute/ep/guidance",
        "EVOLVING_PROFILE_GUIDANCE_CONFIG": "/absolute/user-home/.evolving-profile/guidance-v1/guidance-v1.json"
      }
    }
  }
}
```

保存后按该版本要求刷新/重启应用，查连接日志和聊天里的实际工具，再做一次显式读取。
如果普通 Chat 没有终端/浏览器工具，只给它安装提示词不能让它装系统依赖；后端用获得
授权的 CLI/Code 智能体来装，这里只接 MCP。
官方 `.mcpb` 扩展是一种可用发行方式，但 EP 本包没有这种安装包，不宣传“一键 EP 扩展”。
上述配置不认证自动抓取 Chat 对话、Claude Code Hook 生命周期或全部桌面历史导入。

## 6. 接入后可直接发的验收话

> 检查当前会话实际可用的 EP MCP 工具，需要时为本条原始 Prompt 建立绑定。
> 读取一条与当前任务相关的用户记忆或智能体记忆路线，情景摘要和原文按证据缺口使用。
> 分别报告工具名、返回条数、原文回读和可观察送达；新 Bank 为空或路线不可用可以如实报告。
> 不编造命中，不复用别的 Prompt 的 check ID，不写入合成记忆，不把工具枚举说成全自动接入。

完整验收见[部署指南](DEPLOYMENT-中文.md#7-验收和排错)。宿主行为、协议结果和业务回执分开记录。

## 官方参考（2026-10-17 核对）

- [Codex MCP](https://developers.openai.com/codex/mcp)、[Hooks](https://developers.openai.com/codex/hooks)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)、[Hooks](https://code.claude.com/docs/en/hooks)
- [Claude Code 桌面配置](https://code.claude.com/docs/en/desktop#shared-configuration)
- [Claude Desktop 本地 MCP 与扩展](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)

以上说明宿主能力，不是 EP 完整适配证书。
