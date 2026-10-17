# Local setup / 本地安装与启动

## One command: build, not launch / 一条命令：构建，不是启动

Use a new source checkout with Python 3.11+, `uv`, Node.js **20.9+** and npm:

```bash
./scripts/install-ep51.sh --mode local --no-launch
```

The installer installs base dependencies, builds the workspace client SDK before
the Console, packages the production Console and records a launch manifest. It
creates `.env` only when absent. **It does not start services, create a database,
configure a Provider, register MCP/Hook or import memory.** Omitting `--no-launch`
does not start services either.

中文：首次安装不要用 `--skip-deps`。安装构建完成不等于服务已运行。密钥、数据库、
向量模型需自行配置；不会复制作者的 Bank、对话、配置或本地模型文件。

- `--dry-run`: prints commands; no `.env`, temp backups or build changes.
- `--skip-deps`: only for dependencies already installed in this checkout.
- macOS is the platform exercised locally. Linux is a supported target, but its
  database binaries/system prerequisites need target-machine validation.
- This is not a Windows-native or completely offline installation claim.

## Configure and launch / 配置与启动

Follow [API setup](../api/README.md), fill the generated `.env` locally, and
prepare PostgreSQL/pgvector or explicitly install the `embedded-db` extra.
Chat and embedding endpoints may use different keys/models. Base `uv sync`
does not install embedded PostgreSQL or the local ML stack.

In terminal 1, from the repository root after configuration:

```bash
uv run --project api evolving-profile-api --host 127.0.0.1 --port 8888 --workers 1
```

In terminal 2, from the repository root after building:

```bash
node --env-file=.env console/bin/cli.js --hostname 127.0.0.1 --port 9999 --api-url http://127.0.0.1:8888
```

Open `http://127.0.0.1:9999`; `/en` and `/zh-CN` select English and Simplified
Chinese. Verify API `/health`, Bank listing, actual page rendering and clicks.
If a port is occupied, choose another free port and update the Console API URL
consistently; do not terminate an unrelated listener. A new Bank being empty is
normal. Optional services being unavailable is not zero data or a healthy host.

The API discovers `.env` from its working directory/parents with override
semantics; a conflicting blank template can override an exported value. The
production Console CLI does not load the root `.env` automatically, hence the
explicit Node `--env-file`. Bind locally; public exposure needs separate access
control. Do not commit real `.env` files.

中文：网页打开、API 健康、模型连通、实际召回、宿主送达是不同验收项。只启动 API
和 Console，不能宣称完整 EP 已接入 Codex。Controller、Hook、Guidance 和摘要 Worker
是独立服务；缺失时显示不可用/未知。宿主接入按仓库的适配说明另行核验，不能把
数据平面 `/mcp` 握手等同于完整 `user_recall`、`agent_research` 与 Hook 自动记录。

JEV, external RAG, cloud backup and experimental whole-history model trials are
not enabled by this installer. No production memory or credentials are shipped.

## Host adapter and worker templates / 宿主与 Worker 模板

The published Python entries locate bundled Guidance relative to their own
package, and user configuration below the current user's home. Explicit
`EVOLVING_PROFILE_GUIDANCE_SRC` / `EVOLVING_PROFILE_GUIDANCE_CONFIG` overrides
must use the intended installation's paths; do not copy an author's absolute
path. The local recall-policy bridge also loads the bundled Guidance module.

The macOS `host-adapter/com.evolving-profile.*.plist` files are **templates**.
Their `__EP_HOME__` placeholder must be rendered to your actual home, and Python,
script and log paths verified before any `launchctl bootstrap`. They are not
installed by `install-ep51.sh`; never load the unresolved template directly.
Only register one intended EP controller entry, not duplicate legacy aliases.

中文：宿主入口、Controller、Hook、后台 Worker 与 API/Console 是不同的接入步骤。
发行包不再依赖作者本机 Guidance 源文件；已有用户应保留自己的状态目录、Bank 和配置。
旧内部回放夹具为可选资源，可用 `EVOLVING_PROFILE_LEGACY_REPLAY_FIXTURES` 明确指定；
没有夹具就保持不可用，不能因此导入作者私有文件或宣称回放已通过。

Historical EP2.1 rollback-drill tests require separately supplied
`EP_LEGACY_ROLLBACK_SCRIPT` and `EP_LEGACY_ROLLBACK_BASELINE`. They are optional
external integration assets, not this release's installer. Without them the two
historical cases are explicitly skipped; current EP5.1 installer/rollback tests
do not depend on an author's private backup. Do not point a drill at production.

## Upgrade and rollback / 升级、失败与回退

1. Preserve the prior source, lockfiles, configuration and database backup. Stop
   only services owned by this installation before replacing its builds.
2. Run the installer in the intended checkout. Previous SDK, `.next` and
   `standalone` builds are backed up outside the source tree; the launch manifest
   records their location. Existing `.env` and data are not replaced.
3. A failed build exits nonzero and restores completed prior build backups.
   Failed new artifacts remain available for diagnosis. Incomplete rollback is
   an explicit error, not reported as a successful restoration.
4. If a successful new runtime must be rolled back, stop its own services,
   restore the old matching source/dependency/build set and verify health/UI.
   Build rollback is not automatic database downgrade or dependency rollback.

中文：旧构建可恢复不代表任何数据库迁移都能自动回退。数据恢复要单独校验，不能
用旧队列覆盖新产生或已完成的写入。依赖下载需要网络；本地模型和大规模历史提炼
不会因运行安装器而自动开启。
