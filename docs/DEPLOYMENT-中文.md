# 从源码部署到宿主接入

[English](DEPLOYMENT.md) · [分宿主安装](HOST-SETUP-中文.md) · [给 Agent 的提示词](AGENT-SETUP-中文.md)

本指南面向**新装、本地 macOS**；Linux 要另查系统依赖，未认证 Windows 原生或云端部署。
产品版本读 [VERSION](../VERSION)。为续接现有贡献 PR，分支仍叫 `release/5.1.0`，
分支名称不等于当前补丁版本。发行包不带作者的记忆、账号、密钥、对话或模型权重。

本候选使用精确`v5.1.2-rc.1`标签或对应命名核验归档，见[候选安装入口](CANDIDATE-SETUP.md)，
不能用旧分支或旧Tag替代。安装后继续让Agent阅读[日常操作协议](AGENT-USAGE-中文.md)。
确认当前进程实际加载候选后，按[运行版本投影步骤](CANDIDATE-SETUP.md#project-verified-version-metadata-into-the-selected-runtime)
显式更新所选state root；只构建不能自动覆盖已有安装的版本清单。

## 先选需要达到的程度

| 程度 | 实际组成 | 还不能据此认定 |
| --- | --- | --- |
| A：后端和网页 | 数据库、API、Console | 已接入 Agent、能自动记录 |
| B：显式工具调用 | A + Controller + 宿主 MCP 注册 | 已安装 Prompt Hook、后台能自动提炼 |
| C：日常自动化 | B + 经审查的 Hook + 已配置 Worker | 所有历史均完成、每次回答都受益 |

先验收 A，再验收 B。C 必须用目标宿主上的真实任务验证事件格式、来源身份、写入策略和回执。
Claude Code CLI、桌面 **Code** 页、普通 Claude Desktop **Chat** 必须分开。
已有“一键安装构建”；没有把所有宿主全部配置好的统一一键部署器。

## 1. 准备环境和源码

通过官方渠道准备 Git、Python3.11+、`uv`、Node20.9+、npm，以及 PostgreSQL/pgvector。
准备自己的聊天模型和向量服务；Coding Plan 的聊天 Key 不一定能调向量接口。
本地模型要另装对应依赖、检查内存并实测加载，不由安装器自动下载。

```bash
cd /path/to/extracted-evolving-profile
./scripts/install-ep51.sh --mode local --no-launch
```

脚本预检、安装基础依赖，先构建 SDK 再构建 Console；`.env` 不存在时才创建模板。
它不会安装所有系统环境、创建数据库、拉起服务、注册宿主或开启外部 RAG/JEV/云备份。
`--dry-run` 是无写入预演，首次安装不要 `--skip-deps`。
脚本名字表示5.1系列，具体补丁读 VERSION。升级与回退见 [LOCAL-SETUP.md](LOCAL-SETUP.md)。

## 2. 在本机填配置，统一 Bank

用本地编辑器修改生成的 `.env`，不要在公开对话或 Git 中填写真实凭据：

| 字段 | 用途 |
| --- | --- |
| `EVOLVING_PROFILE_API_DATABASE_URL` | 自己的 PostgreSQL/pgvector 地址 |
| `EVOLVING_PROFILE_API_LLM_PROVIDER`、`_MODEL`、`_BASE_URL`、`_API_KEY` | EP 后台提炼模型，与 Codex/Claude 自己的账号不是一回事 |
| `EVOLVING_PROFILE_API_EMBEDDINGS_PROVIDER` 和相应提供商字段 | 单独验证过的向量模型接口 |
| `EVOLVING_PROFILE_API_RERANKER_PROVIDER=rrf` | 不下载学习型 Reranker 的秩融合，不等于交叉编码器重排 |
| `EP_BANK_ID=personal-memory` | 本指南的安装约定，不是能覆盖所有组件的全局环境开关 |

按 [API 配置](../api/README.md) 查不同提供商字段。内嵌数据库要明确执行
`uv sync --project api --extra embedded-db` 并设置相应数据库 URL；基础依赖不包含它。
不要为了“全功能”盲目装全部 ML extras。

**复制本指南时先使用 `personal-memory`。** API 启动后在网页创建/选择这个 Bank。
当前 stdio 适配器仍有固定 Bank 常量，只改网页选择器或 `EP_BANK_ID` 不会切换它。
使用其他 Bank 的部署必须逐项对齐适配器、访问策略、Guidance、Worker 和 Console，
并检查实际回执里的 Bank ID，不能靠环境变量名字猜测生效。

注册 MCP 的命令不需要填后台模型密钥。网页里显示星号也不等于 API 已加载真实 Key。
已有安装保留自己的配置和状态，下面的新装示例不用于覆盖旧安装。

## 3. 准备 Controller 和 Guidance

发行包提供可直接引用的最小配置：
[Controller 合约](../config/install-controller-contract.example.json)、
[访问策略](../config/install-access-policy.example.json)。
它们用于基础受控路由，不启用实验 memory-OS 或作者以前的 fast-recall 快照；不含私人数据。

首次创建 Guidance 空库配置。以下命令从源码目录执行，已有同名配置时会拒绝覆盖：

```bash
python3 - <<'PY'
import json
from pathlib import Path
root = Path.home() / '.evolving-profile/guidance-v1'
root.mkdir(parents=True, exist_ok=True)
config = root / 'guidance-v1.json'
with config.open('x', encoding='utf-8') as stream:
    json.dump({'registry': str(root / 'guidance.sqlite3'),
               'bank_id': 'personal-memory'}, stream, indent=2)
PY
```

出现 `FileExistsError` 时应检查和复用原配置，不能删掉或改成别的 Bank。
新库偏好为空正常；安装不能靠复制作者的偏好“填满”。
如果 Worker 使用 `.env` 中的 Guidance 字段，把相对路径改成实际源码 `/guidance`
和上面配置的绝对路径。后续 MCP 注册命令会单独传入绝对路径，不依赖工作目录。

## 4. 拉起后端和网页

开三个终端，都进入安装源码目录。它们是前台服务，关闭对应终端就会停。
端口占用时先查属于谁，选空闲端口并同步全部相关地址；不停止无关进程。

**终端1：API**

```bash
uv run --project api --env-file .env evolving-profile-api --host 127.0.0.1 --port 8888 --workers 1
```

**终端2：QueryController**

```bash
HAM_OS_STATE_ROOT="$HOME/.evolving-profile/memory-os" \
uv run --project api --env-file .env python controller/controller.py \
  --host 127.0.0.1 --port 12079 --upstream http://127.0.0.1:8888 \
  --contract config/install-controller-contract.example.json \
  --policy config/install-access-policy.example.json
```

Controller 转发 API 并增加受控查询，不是另一个记忆数据库。
已有部署应使用自己已审查的合约/策略；不能为了消除错误覆盖成最小示例。

**终端3：生产 Console**

```bash
EVOLVING_PROFILE_RECOVERY_SCRIPT="$(pwd -P)/host-adapter/memory_recovery.py" \
EVOLVING_PROFILE_PYTHON="$(pwd -P)/api/.venv/bin/python" \
node --env-file=.env console/bin/cli.js --hostname 127.0.0.1 --port 9999 --api-url http://127.0.0.1:8888
```

打开[简体中文](http://127.0.0.1:9999/zh-CN)或[English](http://127.0.0.1:9999/en)。
macOS 可执行 `open http://127.0.0.1:9999/zh-CN`；Linux 使用桌面浏览器打开方式。
再检查：

```bash
curl --fail http://127.0.0.1:8888/health
curl --fail http://127.0.0.1:12079/v1/status
```

API、数据库、模型通路、网页点击和宿主工具是不同验收项。两个服务就绪后，再做
[宿主注册](HOST-SETUP-中文.md)。API `/mcp` 不等于 EP Controller 的 stdio 工具。
端口保持本机回环访问，不为了“能连接”公开服务或取消宿主权限保护。

Console 命令前两个环境字段把网页恢复 runner 绑定到本安装真实的解释器和脚本；
新装生产 standalone 若没有这些值，可能找不到正确路径。它们不会授权恢复作业，
也不会让所有旧的受管服务控制自动适配手动部署。

## 5. 网页配置怎么调

先选择自己的 Bank，再进入**记忆库配置**。下面是新用户的建议，不是说所有启动方式
都支持同样的自动应用；标签随界面语言变化。

| 区域 | 建议起点 | 必须核对 |
| --- | --- | --- |
| Provider | 先测通主模型，再配置独立测通的 fallback | 保存/重载后后端实际使用的模型、Base URL 和凭据状态 |
| 用户记忆、智能体记忆 | 保留需要的模块，用不到再关 | 记录、检索、注入是不同开关；开启不等于缺失的 Worker 已启动 |
| 相关度 | 从当前弱相关/背景友好策略开始 | 完全无关仍排除；弱相关候选不能自动当事实 |
| 向量与重排模型 | 先验证线上向量或本地真实加载 | 索引的模型和维度一致；换模型需要重建，不是直接复用旧向量 |
| 情景摘要 | 分层导航，不够再有限回读原文 | 来源版本、范围与覆盖；不默认扫描提炼全部历史 |
| 外部 RAG | 有明确资料文件夹和集合时才开 | 索引、模型绑定和来源隔离；选目录不是把文件自动变成个人记忆 |
| JEV | 初装先关，测通后按需开启辅助环节 | 要看到真实判断记录；失败用规则托底，风险门独立选择 |
| 备份 | 先本地、设置保留策略，再检查恢复证据 | 任务已计划不等于备份已验证；云端仍可选 |

**特别注意配置生效位置：**上述手动 API 命令读源码目录的 `.env`；网页受管 Provider
通常生成 `~/.evolving-profile/profiles/evolving-profile-api.env`。两者不自动相等。
“保存成功”不能直接说成“后端已应用”。手动部署要备份并更新其自己的 `.env`、只重启
该安装的 API；或按受管流程指定并验证实际加载的 profile。不要把网页遮罩字符复制成 Key。

状态目录和服务控制是本机操作员的配置。`EVOLVING_PROFILE_STATE_ROOT` 指向别处时，
表示另一套安装，不是可以控制默认目录守护进程。部分宿主读取器仍以用户家目录定位，
单改该变量也不代表完成多实例隔离。

**链路图布局：**点链路页齿轮→保存布局。坐标写入本安装状态目录的
`config/topology-layout.json`，页面显示共享修订号；不再由各网址/端口各自保存一套权威坐标。
旧 v7 浏览器布局保留为可明确载入的未保存草稿，载入不等于发布；旧页面不能覆盖新版。
自定义文字按语言隔离。极端进程崩溃若留下保存锁，界面会报忙，不自动破坏其他写入者的锁；
恢复前核实所属进程已退出，保留当前布局与 `.previous`，不能清空状态制造正常。
不同状态根目录是不同安装，也不代表不同电脑之间自动共享。

## 6. 自动记录、提炼和后台任务

显式 MCP 查询和自动化分开。[宿主说明](HOST-SETUP-中文.md)提供 Codex Hook 及 Claude
复用边界。完成来源捕获验证后，留存队列的调度命令是：

```bash
uv run --project api --env-file .env python host-adapter/retention_worker.py --once
```

此入口执行**一轮**调度，不写 `--once` 也不会自动变常驻服务。按本安装配置定时运行，
保留失败和隔离记录，检查远端操作真正完成。它读取自己的 `~/.evolving-profile/codex.json`，
不能假定 Bank 网页切换或 `EP_BANK_ID` 已设置其 API 地址和队列。

先只看 Codex 情景作业状态，不触发模型提炼：

```bash
uv run --project api --env-file .env python host-adapter/context-incremental-worker.py --status
```

要处理明确选中的近期 Codex 会话，先以 `--discover-only` 加 `--session-root`、
`--session-id`、`--bank-id` 检查来源范围；确认后才用同一范围加
`--process --max-jobs 1 --provider-env /absolute/local/provider.env`。
`--process` 会使用模型额度，不能把 Codex 扫描器指向 Claude 对话目录就认为兼容。

其他 Worker 有各自的输入和配置归属，也不会由安装器启动。仅为已选择的能力、在源码目录执行：

| 入口 | 实际输入与行为 |
| --- | --- |
| Guidance | 用户目录 Guidance 配置、来源 API、Bank 和 `EVOLVING_PROFILE_PROFILE_ENV` 文件；一轮可能处理全部已变化观察，不是带 `--limit` 的小批次 |
| 主题地图 | `.env` 数据库、明确 Bank、输出 SQLite 路径；`--limit 500` 只限制抓取清单，不代表全历史语义完成 |
| 状态服务 | 源码 runtime root、API8888、Controller12079；这里服务端口用12098，不是9998 |
| 恢复 | 已存在且明确选定的作业，不表示全局重试/清零 |

**Guidance：只用于空的新 Bank，或明确允许处理全部已变化观察时：**

```bash
EVOLVING_PROFILE_PROFILE_ENV="$(pwd -P)/.env" \
EVOLVING_PROFILE_SOURCE_API_URL=http://127.0.0.1:8888 \
EVOLVING_PROFILE_BANK_ID=personal-memory \
uv run --project api --env-file .env python guidance/guidance_worker.py
```

这个脚本自己读取 profile 文件，仅导出 shell 变量不够。旧解析器需要普通 `KEY=value`，
不要用 shell 表达式或 `export` 行；运行可能消耗模型额度并重建派生心智模型。
不能拿已有大 Bank 的全量变化观察当“启动测试”。

**主题地图：数据库连接配置好后：**

```bash
uv run --project api --env-file .env python guidance/topic_catalog_worker.py \
  --bank-id personal-memory --limit 500 --output "$HOME/.evolving-profile/catalog/topics.sqlite3"
```

**状态服务：另开本安装自己的终端：**

```bash
EVOLVING_PROFILE_RUNTIME_ROOT="$(pwd -P)" \
EVOLVING_PROFILE_API_URL=http://127.0.0.1:8888 \
EVOLVING_PROFILE_CONTROLLER_URL=http://127.0.0.1:12079 \
EVOLVING_PROFILE_STATUS_PORT=12098 \
uv run --project api --env-file .env python status/evolving_profile_status_server.py
```

启动 Console 前，在其自己的 `.env` 设
`EVOLVING_PROFILE_STATUS_API_URL=http://127.0.0.1:12098`；部分旧路由否则默认9998。
只重启这套 Console 以加载环境。Controller 查 `/v1/status`，不要编造状态服务 `/health`。
面板没有证据时仍是未知。

恢复优先从网页“补录与提炼”检查有范围的计划和实际作业 ID。已有批准作业可用
`uv run --project api --env-file .env python host-adapter/memory_recovery.py --run-job REAL_JOB_UUID`，
先替换为持久作业的真实 UUID；它不是开机检查，也不用于把已完成操作换 ID 重交。
是否消耗模型、写什么内容取决于该作业。每个入口先验证自己的周期，再计划运行，
不把缺失的可选服务说成正常。
macOS plist 是模板：要替换全部 `__EP_HOME__`，将示例中的历史起始日期改成明确选定的
新安装时间；不能原样加载模板或默认重提炼全部旧历史。

## 7. 验收和排错

每个宿主分别记录“通过、失败、不可用、未测试”：

1. API 健康、数据库和实际配置模型的连通。
2. 选定语言网页显示与点击；新 Bank 为空正常。
3. Controller 状态和指向的 API 正确。
4. 宿主原生工具列表和真实任务调用，而不是配置文件里有名字。
5. 候选、返回正文、原文回读、送达分别核对。
6. 若开启自动记录，验证允许记录的自然任务：捕获→队列→提炼完成→网页可见。
   不向生产库塞测试内容。
7. 链路页能对应这次 Prompt；没有证据的答案采用保持未知。

看不到工具先查绝对路径、环境和重复服务，再判断是否需要刷新宿主；工具能调但为空，
查 Bank、来源覆盖、模块和相关度，不直接判为连接坏了。网页保存没影响后端，先查配置
归属。智能体分类为空应查合格来源，不能制造合成“成功经验”补数字。

另读[依赖风险](DEPENDENCY-RISKS.md)、[发布记录](RELEASE-LEDGER.md)。本文不代表所有
宿主、平台、历史或未来模型响应都已验证，也不移动旧标签。

## 8. 如何停止、重启和备份

上述前台进程在其终端按 **Ctrl-C** 停止。先停本安装的捕获/调度；在途写入等待完成或保留
操作 ID。按需停本套 Console/状态服务/Controller，再停 API。不批量杀所有 Python/Node，
不取消无关作业。重启按 API→Controller→状态服务（如用）→Console，保持相同有效配置，
再次查健康、网页和宿主。stdio MCP 由宿主拥有，不是应另留后台的服务器；换可执行路径
时检查注册和目录是否需要刷新。

手动本地备份选一个私有、持久目录，创建唯一的新备份夹。以下只保存配置/派生队列，
**不代替数据库备份**：

**归档前必须暂停本安装的全部写入方**：Hook、MCP、留存/Guidance/情景/恢复 Worker，
以及网页设置保存，不只是 API；等待或保留在途作业。无法暂停时，使用数据库支持的
一致性在线备份/快照，不能对仍在写的 SQLite 做普通 tar。下面命令以已满足此条件为前提。

```bash
EP_BACKUP_PARENT="$HOME/EP-backups"
mkdir -p "$EP_BACKUP_PARENT"
EP_BACKUP_DIR="$(mktemp -d "$EP_BACKUP_PARENT/ep-XXXXXX")"
chmod 700 "$EP_BACKUP_DIR"
test ! -f .env || cp -p .env "$EP_BACKUP_DIR/checkout.env"
test ! -d "$HOME/.evolving-profile" || tar --exclude='.evolving-profile/backups' \
  --exclude='.evolving-profile/runtime' -czf "$EP_BACKUP_DIR/operator-state.tgz" \
  -C "$HOME" .evolving-profile
git rev-parse HEAD > "$EP_BACKUP_DIR/source-commit.txt"
cp VERSION package-lock.json "$EP_BACKUP_DIR/"
chmod -R go-rwx "$EP_BACKUP_DIR"
```

状态包可能很大，先估算空间。另存这次修改的宿主 MCP/Hook/settings 文件：Codex 的
`config.toml`/`hooks.json`，Claude 用户/项目设置或 Desktop JSON，以及本安装的服务定义、
放在其他位置的有效 Provider profile。旧构建或安装器生成的备份路径也保留，以便代码回退。
**这些包含密钥和私人记忆，不能传 GitHub、Issue 或公开 Agent。**

PostgreSQL 单独用数据库客户端/DBA 或匹配版本的 `pg_dump` 备份。例如先把本地 libpq
服务 `ep-local` 配到正确数据库，并安全保存认证，再运行
`pg_dump --format=custom --file="$EP_BACKUP_DIR/database.dump" --dbname=service=ep-local`。
`ep-local` 是需自行准备的模板名称，不是 EP 自动创建；不要把含密码 URL 粘进公共命令。
检查退出0和 `pg_restore --list`，只在**独立的可丢弃数据库**做恢复演练。
能列出备份目录不等于恢复已验证，文件 tar 更不是运行中 PostgreSQL 的可靠备份。

内嵌 `pg0` 要从该实例的配置/日志查实际数据目录、端口和匹配的 PostgreSQL 工具，
外部数据库的 `ep-local` 示例不会替它配置连接。应从正确实例逻辑导出，或使用引擎
支持的停机数据备份；不能复制运行中的内嵌目录，也不能假定状态 tar 已覆盖其数据库。
两种备份路线都未准备好时，如实标记备份/升级验收未完成。

恢复前保留新写入，不用旧队列覆盖已完成操作；先核对代码/构建/配置与数据库版本。
网页保留策略不能替代首次恢复验收。初装要检查云端开关：某些历史默认配置会显示 WPS
镜像已启用，这不代表已安装上传器；未选择云备份就保持关闭，不因此启动云任务。
已安装5.1.0与待发布5.1.1存在差异可以正常；本机状态审计为显式选择的集成检查
（`EP_TEST_LIVE_STATE_AUDIT=1`），不能为了过测试擅改运行状态。
