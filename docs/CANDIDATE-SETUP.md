# Install this candidate, not an older remote branch / 候选包安装入口

[English overview](../README.md) · [中文介绍](../README-中文.md) · [Agent usage](AGENT-USAGE.md)

Use the exact **v5.1.2-rc.1** tag or the named verified archives on its
[release page](https://github.com/ccygod/evolving-profile-2.2/releases/tag/v5.1.2-rc.1).
Read VERSION and the manifest. A contribution PR is not an upstream merge or stable Release;
actual states belong in the release ledger. Never substitute an older public branch.

本目录是**5.1.2 RC1候选版**，从精确标签或对应命名核验归档读取VERSION与发行清单。
旧远端分支、旧下载链接和宿主能连上的事实，都不能证明已经装了这个候选包。

## macOS source setup

Extract to a new directory. First inspect the archive paths and checksum; never extract over
an existing installation. Requirements and backend credentials are listed in README and
[DEPLOYMENT.md](DEPLOYMENT.md). From the extracted root:

```bash
python3 scripts/release-preflight.py --root . --json
./scripts/install-ep51.sh --mode local --dry-run --no-launch
./scripts/install-ep51.sh --mode local --no-launch
```

The first checks metadata, dry-run makes no files, real setup installs dependencies/builds and
creates `.env` only when absent. It does **not** start services or register a host. The filename
is historical; actual product version is read from VERSION. `--skip-deps` is only for already
provisioned dependencies. Do not use it to conceal a failed first install.

Next supply your own database/chat/embedding configuration safely, then use
[the documented API, QueryController and Console commands](DEPLOYMENT.md#4-start-backend-and-web-ui).
The Console launcher preserves the colocated EP script root after entering standalone; an
operator-provided `EVOLVING_PROFILE_HOST_SOURCE_ROOT` still wins. When starting `standalone/server.js`
directly or deploying Console separately, explicitly set that root to the full preparation package
and `EVOLVING_PROFILE_PYTHON` to its actual interpreter. Never leave a development-machine path.

Open your chosen Console address, select your own Bank, verify health and real page controls.
Only then inspect/register **one** intended host entry using the per-host instructions. Match
Bank IDs, API URLs, Controller policy and configuration scope; a dropdown change is not a migration.

## Project verified version metadata into the selected runtime

The package VERSION/manifest is authoritative; the runtime display reads a checked copy in the
selected state root. A build does not modify global runtime metadata. First verify that the intended
Console process actually loaded this candidate's build/directory. For an existing installation,
do not relabel an old running program by copying metadata early.

Choose the actual installation state root, keep it consistent for Console and the intended
services, and inspect a zero-write preview. Example for the normal operator-owned default:

```bash
export EVOLVING_PROFILE_STATE_ROOT="$HOME/.evolving-profile"
api/.venv/bin/python scripts/project-release-metadata.py --state-root "$EVOLVING_PROFILE_STATE_ROOT"
```

Only for a genuinely absent target, after reviewing the preview:

```bash
api/.venv/bin/python scripts/project-release-metadata.py --state-root "$EVOLVING_PROFILE_STATE_ROOT" --apply --expected-sha256 absent
```

For an existing target, replace `absent` with the preview's exact before_sha256 after review.
The command rejects changed revisions/source-version mismatches, preserves the prior projection
as a backup and does not change other settings. A different state root is a separate installation,
not a way to relabel or control default services. Custom host/Guidance/session paths still need
their own consistent configuration; changing one state variable is not a complete migration.

Read `/api/evolving-profile/runtime` and, with the data API available, `/api/version`; check
product_version and channel against the package. This display check does not prove every
service/model/host was upgraded. Always pass `--hostname 127.0.0.1` to the Console command:
the legacy bare CLI still defaults to all interfaces; this candidate does not silently change it.

中文：构建不改全局运行版本。确认当前进程确实加载候选包后，预览并显式投影到同一个
state root；新目标才用absent，旧目标必须审阅并提供当前哈希。旧清单有备份，冲突拒绝覆盖。
不要提前把旧程序贴成新版本，不用别的state root绕过真实安装。裸CLI默认监听范围仍是
遗留限制，文档命令明确绑定127.0.0.1；运行版本显示正确也不等于全宿主已升级。

## Preparation commands without real host tasks

After Python dependencies are provisioned, from this candidate root:

```bash
api/.venv/bin/python scripts/ep-host.py list --json
api/.venv/bin/python scripts/ep-host.py doctor --host doubao_work --json
api/.venv/bin/python scripts/ep-host.py config-preview --host workbuddy --json
api/.venv/bin/python scripts/ep-host.py guide --host doubao_work --locale zh-CN --json
```

Default doctor/discovery/preview do not apply host config. An explicit doctor `--probe` performs
isolated EP initialize/list and saves preparation diagnostics; it is not a native client test.
The web Host integrations page has the same boundary. Apply/Restore buttons stay disabled in
preparation mode; reviewed CLI application requires its plan, revision check and confirmation.

## Windows / WSL / remote

See [Windows preparation](host-integrations/WINDOWS-中文.md). Do not present the Bash installer
as a certified native PowerShell installer. With a provisioned Python3.11+ interpreter:

```powershell
./scripts/ep-host.ps1 list --json
./scripts/ep-host.ps1 doctor --host workbuddy --json
```

Native Windows, WSL and remote are separate execution modes. No blanket ExecutionPolicy bypass,
administrator privilege, public port or downloaded script execution is required by this guide.
The prepared manual CI is not an executed Windows receipt. Real host/model tests remain separate.

## Upgrade / failure / rollback

Use a new extracted directory and preserve the current program/config/data. Do not point services
at the candidate before build and dependency verification. The existing installer backs up old
builds and retains failed artifacts; see [LOCAL-SETUP.md](LOCAL-SETUP.md). That build recovery is
not a database restore or a host-configuration rollback. Configuration apply/restore separately
checks expected hashes and refuses to overwrite later user edits.

Confirm the actual running directory/build after switching only owned services. On failure, restore
the previous program/launch pointer, not memory contents. Keep user topology calibration, provider
keys, other MCP servers and history intact. Never run whole-history extraction as an installation test.

## 中文给Agent的一句话

```text
请使用我提供的EP候选包目录，先核对VERSION和发行清单，不要用旧远端分支冒充新版本。
阅读README、CANDIDATE-SETUP、对应宿主安装指南和AGENT-USAGE；先预检/构建，再安全配置
我的服务并启动后端与网页。接入前备份并合并已有配置，不重复注册。分别验证构建、服务、
网页、工具、真实绑定及允许启用的生命周期；未测的明确写未测，不安装其他客户端、开启
可选功能或重提炼历史。没有终端/浏览器/凭据就说明缺口，不编造已经完成。
```
