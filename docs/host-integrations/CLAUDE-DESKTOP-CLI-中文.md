# Claude Desktop / Claude CLI 与 Evolving Profile

从 5.1.3 起，Evolving Profile 随包提供一套**按宿主自适应**的接入套件（`claude-code/`），让 **Claude Desktop（Cowork／本地智能体会话）**、
**Claude Code CLI** 与 **Codex** 共用同一个 EP Bank。本页说明它做了什么、怎么安装与验证、各部件失败时会怎样，以及哪些事**没有**被证明。
[English](CLAUDE-DESKTOP-CLI.md)

> 证据范围：在**一台 macOS 机器**上，用 Claude Desktop 3P（Cowork）、本机 EP 和真实 Bank 开发并运行。Claude **CLI** 这一路是用模拟宿主标记
> （`CLAUDE_CODE_ENTRYPOINT=cli`）经真实桥接脚本验证的，**没有**在真实 CLI 会话里跑过；Windows、Linux 未测。见[已知边界](#已知边界)。

## 1. 解决什么问题

EP 的钩子和存储最初围绕 Codex 设计。把别的宿主直接接上去，会出现下面这些实际观察到的问题：

| 现象 | 原因 | 5.1.3 的做法 |
| --- | --- | --- |
| Claude Desktop 的对话进不了 Bank | Desktop 会话不读 `~/.claude/settings.json`，没有钩子入口 | 用一个很薄的**组织插件**声明六个生命周期钩子，统一调用同一个桥接脚本 |
| 工具输出（文件转储、`cat -n` 列表、命令结果）被当成“用户说过的话”存下来 | 旧 CLI 桥把 `tool_result` 拍平成了 `user` 文本 | 只保留人能看到的对话；`tool_use`、`tool_result`、思考、图片、子链路、系统提醒都丢弃 |
| Claude 忽略了召回上下文 | 旧桥输出的是顶层 `additionalContext` | 改为 `{"hookSpecificOutput": {"hookEventName": …, "additionalContext": …}}` |
| 适配器分不清宿主 | 只设置了 `EVOLVING_PROFILE_AGENT_NAME`，而适配器读的是 `HINDSIGHT_AGENT_NAME` | 两个变量都设置，值来自自动宿主识别 |
| Desktop 对话看不到情景摘要 | 摘要管线只读 Codex 的 rollout 文件 | `desktop_rollout.py` 把对话转成 Codex 格式 rollout，写入 EP 自己的 `claude-code/rollouts/`（绝不写 `~/.codex`） |
| 大量事实提炼批次被隔离 | 模型返回的引文“几乎逐字”，校验器按字节严格比较，重试又发送同样输入 | 加入确定性的**引文修复**（见下），失败时保持拒绝 |
| 每轮重复注入约 4.3 KB 相同说明 | 钩子每轮重发记忆使用说明 | 会话开始时给完整版，之后换成一行占位 |

## 2. 结构

```
Claude Desktop (Cowork) ──组织插件──┐
Claude Code CLI ── ~/.claude/settings ─┼─► hook_bridge_desktop.py ─► host-adapter/{session_start,recall,pre_tool_use,
Codex（不变，用自己的钩子）──────────┘     detect_host()              post_tool_use,pre_compact,retain}.py ─► EP API / Bank
                                           normalize_transcript()
                                           desktop_rollout.py ─► claude-code/rollouts/ ─► 情景摘要管线
```

* **`hook_bridge_desktop.py`**：唯一入口，`python hook_bridge_desktop.py <session|recall|pretool|posttool|precompact|retain>`。它**绝不阻塞 Claude**：任何失败只写入
  `claude-code/desktop-hook.log`（事件、载荷*键名*、耗时、退出码，不含内容），进程始终退出 0；PreToolUse 不输出允许/拒绝决定。
* **`hook_bridge.py`**：指向上面文件的 `runpy` 薄壳，让仍写着 `hook_bridge.py` 的旧 CLI 配置也得到修复后的行为。
* **`desktop_rollout.py`**：对话 → Codex 格式 rollout，带 **20 分钟静置期**——后台摘要器正在处理时改写 rollout 会使其任务失效，所以更新先打标记（`rollouts-pending/`），等文件安静后在之后的会话/提示/停止事件里补写。
  定时任务包装出来的会话（`<scheduled-task`、`[SCHEDULED TASK - AUTOMATED FIRING`）会被跳过。关闭开关：创建 `claude-code/desktop-rollout.off`。
* **`compat/desktop_compat_patches.py`**：对 `host-adapter/` 的四处小改动，幂等（本发行包已应用；这个工具用于升级旧安装，并让 `check` 能发现 EP 升级后补丁被悄悄覆盖）：

  | 文件 | 改动 | 目的 |
  | --- | --- | --- |
  | `retain.py` | 队列条目带上 `origin_agent`（取自 `HINDSIGHT_AGENT_NAME`，默认 `codex`） | 捕获时区分宿主 |
  | `retention_worker.py` | 把 `origin_agent` 写入 Bank 元数据 | Bank 侧同样区分 |
  | `recall.py` | prompt-ingress 的 `host_id` 取自同一变量 | 召回回执按宿主区分 |
  | `lib/session_paths.py` | 把 `claude-code/rollouts` 加入 Codex 布局的会话根目录 | 情景摘要能看到 Claude 对话 |

  有意**不改**：`codex-hook-token-batch`、`codex-batch-`、`codex-userpromptsubmit` 这些标识，因为 EP 其他代码依赖它们。已有的 Codex 数据仍是 `origin_agent=codex`。

### 宿主识别（`detect_host()`）

| 顺序 | 信号 | 结果 |
| --- | --- | --- |
| 1 | 环境变量 `EP_HOST`（字母、数字、`-`、`_`，≤ 40 字符） | 该值（手动指定／接入新宿主） |
| 2 | `CLAUDE_CODE_IS_COWORK=1`，或 `CLAUDE_CODE_ENTRYPOINT` 为 `local-agent`／`claude-desktop`／`desktop` | `claude-desktop` |
| 3 | `CLAUDE_CODE_ENTRYPOINT=cli` | `claude-cli` |
| 4 | 其他（SDK、IDE、未来的取值） | `claude-code`，并记录原始 entrypoint，健康检查会提示你补规则 |

结果写入 Bank 的 `origin_agent`、召回回执的 `host_id` 和钩子日志的 `host` 字段。

## 3. 安装

前提：EP 5.1 已能运行（API 在 `127.0.0.1:12079`）、有 Python 3；只有 Desktop 需要一次 `sudo`。

```bash
# 在本仓库的检出目录里
zsh claude-code/install.sh --dry-run               # 列出每一步，不改任何东西
zsh claude-code/install.sh                         # 套件 + host-adapter 改动 + CLI 钩子           （不需要 sudo）
zsh claude-code/install.sh --desktop-plugin        # 再加 Claude Desktop 插件                      （需要一次 sudo）
```

按顺序做的事（`EP_HOME` 默认 `~/.evolving-profile`）：

1. 把 `claude-code/` 复制到 `$EP_HOME/claude-code/`（已有的日志、rollout、transcript 保留）；
2. 对 `$EP_HOME/runtime/host-adapter` 应用四处改动（已改过的跳过；周边代码变了的文件会**拒绝**并说明，需要人工处理；备份 `*.pre-reapply-<时间戳>`）；
3. 设置了 `EP_API_SRC=<API 源码目录>` 时，对 API 源码应用引文修复补丁（本仓库的 API 已包含它）；
4. 把 EP 钩子合并进 `~/.claude/settings.json`（备份 `settings.json.pre-ep-<时间戳>`；其他键和别人的钩子保留；无法解析的文件绝不覆盖）；
5. 带 `--desktop-plugin` 时：用你的 Python 与桥接脚本路径渲染 `desktop-plugin/ep-desktop-bridge/hooks/hooks.json`，复制到
   `/Library/Application Support/Claude/org-plugins/ep-desktop-bridge`（旧版备份为 `.bak-<时间戳>`；文件会设为所有人可读，否则非 root 的 Desktop 读不到）。

然后**完全退出 Claude Desktop（Cmd+Q），重新打开并新开会话**——插件在会话开始时加载。

`zsh claude-code/install.sh --uninstall [--desktop-plugin]` 移除 CLI 钩子（及插件）。升级 EP 代码后需要重启服务，例如
`launchctl kickstart -k gui/$(id -u)/com.evolving-profile.api-shadow`（服务名因部署而异）。

所有步骤都不会动 Codex：`~/.codex/*` 与 `codex.json` 既不读也不写。

### 添加 MCP 服务（读取）

钩子负责*捕获与每轮上下文*。主动读取（`user_recall`、`user_research` 等）还要把 EP 的 MCP 服务注册到宿主，见 [HOST-SETUP-中文.md](../HOST-SETUP-中文.md) 和[宿主矩阵](MATRIX-中文.md)。
Claude Desktop（3P）从它的 `mcpServers` 配置读取。

## 4. 验证

```bash
python3 claude-code/compat/ep_desktop_health.py          # 只读；仅出现 FAIL 时退出码为 1
python3 claude-code/compat/ep_desktop_health.py --json
```

检查项（各为 `OK`／`WARN`／`FAIL`）：API `/health`；补丁是否完整；桥接文件能否编译；Desktop 插件是否在位且 6/6 事件；24 小时钩子活动；rollout 与待写标记；写入队列（**Claude Desktop** 的条目被隔离为 `FAIL`，其他宿主的隔离项为 `WARN`）；
召回回执的 `host_id`；Claude 会话的情景摘要任务；worker 错误日志；**读写嵌入模型是否一致**；以及 24 小时内到达 EP 的 Claude 宿主（出现未识别的新 entrypoint 会提示）。

`WARN` 表示需要看一眼，`FAIL` 表示链路某一环断了。`/health` 的 `functional_status: degraded` 只反映*最近一次*请求，下次成功就恢复。

手动确认钩子触发：发一条提示后看 `tail -n 5 $EP_HOME/claude-code/desktop-hook.log`，新行里应有 `"host": "claude-desktop"`（或 `claude-cli`）。

### 测试

```bash
EP_ADAPTER=$PWD/host-adapter zsh claude-code/compat/run_tests.sh      # 在仓库检出目录
zsh claude-code/compat/run_tests.sh                                   # 针对已安装的 EP
```

在**暂存副本**上运行，HOME 隔离，不改任何线上文件。先查补丁，再跑兼容测试（补丁器、来源标记、桌面根目录、静置期、host-id 标签、自动会话跳过、引文修复、宿主识别矩阵、tool_result 回归、说明去重、CLI 钩子安装器），最后跑 EP 自带的写入重试测试。
本版本的结果见 [RELEASE-NOTES-5.1.3.md](../RELEASE-NOTES-5.1.3.md)。

## 5. 事实提炼的引文修复

EP 只有在 `source_quote` 是*所述作者*原始消息的精确子串时才存事实。模型经常重敲引文时有细小偏差，或者写错 `source_message_index`；整批随后失败，并以完全相同的输入重试，直到被隔离。补丁（`source_attribution.py`）在精确校验前尝试两种**确定性**修复：

1. `exact_quote_index_corrected`：引文逐字出现在所述角色的唯一一条消息里，只是编号写错；
2. `snapped_to_verbatim_span`：引文与所述角色某条消息里**唯一**的一个片段相似度 ≥ 0.90（且比第二名至少高 0.10）；存的是该原文片段，而不是模型的文字。

绝不放宽：作者/角色、有歧义（保持拒绝）、`source_quote_ref` 选择器路径、低于阈值的情况、混入 `cat -n` 行号的片段、超过 1,500 字符的引文。修复来源记录在 `source_quote_resolution`／`source_quote_repair`。
关闭开关：`EVOLVING_PROFILE_API_QUOTE_REPAIR=0`（每次调用时读取）。首次测量中，被拒的近似引文有 87% 与某个唯一片段相似度 ≥ 0.90；对隔离率的*长期*影响尚未测量。

## 6. 运维经验

* **嵌入模型分裂。** 如果 API 启动脚本加载了检索模型覆盖配置而 worker 启动脚本没有，新向量就会在一个空间写入、另一个空间查询；混合检索靠关键词/图谱分支仍“能用”，所以看不到明显报错。健康检查比较两个进程启动时记录的模型，不一致即 `FAIL`（在真实 Bank 上的测量：纯向量检索 top-1 在不一致时 0.01，一致时 0.94——这是个简单任务，只说明存在错配，不代表绝对质量）。覆盖配置导致的情形可用 `compat/fix_embedding_split.sh status|apply|rollback`。
* **LLM 故障切换。** API 支持带编号的额外 provider 加一个策略。同一个 OpenAI 兼容接口、同一个密钥、多个模型的例子：

  ```
  EVOLVING_PROFILE_API_LLM_1_PROVIDER=openai   EVOLVING_PROFILE_API_LLM_1_API_KEY=…   EVOLVING_PROFILE_API_LLM_1_BASE_URL=…   EVOLVING_PROFILE_API_LLM_1_MODEL=<备用模型>
  EVOLVING_PROFILE_API_LLM_STRATEGY='{"mode":"failover"}'
  ```

  JSON 必须加引号：启动脚本在 zsh 里 `source` 这个文件，不加引号的 `{"mode": "failover"}` 会解析失败。同一接口上的多个模型只能防单个模型故障，防不了接口本身不可用。
* **Claude 每次 MCP 调用约 60 秒的上限。** 宿主侧的长任务要做成后台任务再轮询，不要做成一个很长的同步调用。
* **旧桥错误归属的事实。** 如果某条 Bank 记录的 `source_quote` 只出现在原始 Claude 会话的 `tool_result` 里、从未出现在人类输入文本中，可以重新标注而不是删除：先把原元数据存进备份文件，再把 `statement_kind` 改为 `source_repetition`、`independent_user_evidence` 改为 `false`，并记录原值。本套件不随附这个一次性工具；恢复保存的元数据即可撤销。
* **回退。** 每处改动都在文件旁留下 `*.pre-<名称>-<时间戳>`。只想让 Claude 对话不再进入情景摘要：`touch $EP_HOME/claude-code/desktop-rollout.off`。恢复每轮完整说明：`EP_FULL_INSTRUCTION=1`。

## 已知边界

* **CLI**：经真实桥接脚本以模拟宿主标记验证，未在真实 CLI 会话中运行。
* **Desktop 插件**需要一次 `sudo`（系统插件目录）和重启 Desktop；只影响之后新开的会话。
* 所有 Desktop（Cowork）对话共用同一个工作目录（`/private/var/empty`），情景摘要无法按项目分组。
* Desktop 的 rollout 要过静置期才进入情景摘要，不是即时的。
* 引文修复能减少但不能消除被隔离的批次（过长的分块仍可能超过提炼预算）。
* 说明去重只对安装之后新开的会话生效。
* 钩子有活动只证明上下文送达，不证明回答用到了它。
* 仅 macOS；Windows/Linux 路径未测。
