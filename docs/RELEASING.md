# Evolving Profile 发布手册

本文件是下一次更新发行包时的工作清单。产品版本以 `VERSION` 为准；API、Console、MCP 适配器可能有独立组件版本，不能只改一个数字就宣称整包已经升级。当前发行包是脱敏模板，不能从个人运行目录直接整目录复制。

## 仓库和权限边界

- 开发源码与发行仓库分开管理；发布前必须从经过验证的开发工作区选择性同步，不能从个人运行目录整目录复制。
- 脱敏发行仓库是本目录。发布前先确认 `git status`、当前分支及 `origin`、`fork` 的实际 URL，不能从目录名推断 GitHub 仓库名称。
- 上次采用 fork 的 `release/3.0.0` 分支向上游 `main` 提交贡献 PR。今后仍以分支和 PR 为默认路径；推送、创建 PR、Tag 或 GitHub Release 需当次明确授权，不因“准备发布”而自动执行。
- 同步源码时逐模块比较、脱敏并检查差异。个人 Bank、摘要索引、对话、运行回执、缓存、日志、备份、凭据和真实 `.env` 不进入发行包。

## 准备一次更新

1. 核实目标版本、当前上游基线、实际已完成的功能和兼容边界。不要把本机尚未交付到发行仓库的功能写为已发布。
2. 从开发源码选取经过测试的变更，同步到脱敏仓库；先查看差异和新增文件，保留本仓库自己的模板配置与致谢。不要覆盖与任务无关的本地更改。
3. 更新 `VERSION`、README 首行和版本定位、`NOTICE.md`、链路页产品版本标识，并新增 `CHANGELOG-<主版本>.<次版本>.md`。产品版本与组件版本分开说明。
4. 按 [发布说明模板](RELEASE-NOTES-TEMPLATE.md) 写出“解决的问题、实际变更、迁移/兼容、边界、验证、回退”。所有数字来自本次测试和读回，历史成绩不能复用。
5. 用 `git shortlog -sne HEAD` 查看提交身份，再逐项核对 `NOTICE.md` 和上游许可；Git 提交邮箱不自动等于公开署名，不能把致谢项目写成 EP 代码贡献者。作者 CCY 的署名沿用现有 NOTICE，新增贡献者需有可核对来源。
6. 运行下面的预检与测试。任何失败或未知覆盖都写入发布说明，不宣称通过。
7. 审阅 `git diff --check`、`git diff --stat`、`git status --short` 和最终文件清单；确认不存在个人路径、名称、密钥、运行数据或误提交的构建缓存。
8. 当次获得 GitHub 提交授权后，使用新版本分支向上游 `main` 发 PR，附本次发布说明、验证回执与脱敏结论；PR 创建后在当前任务中关联。合并、打 Tag 和创建 GitHub Release 分别核对状态，不把 PR 已合并当成 Release 已发布。

## 本地预检

在本发行仓库根目录运行：

```bash
python3 -m unittest scripts/test_release_preflight.py
python3 scripts/release-preflight.py --json
./scripts/verify-package.sh
git diff --check
git status --short
```

`release-preflight.py` 会检查产品版本在 VERSION、README、NOTICE、CHANGELOG 和链路页标识中是否一致，并打印当前分支、远端和提交作者快照。`verify-package.sh` 再检查结构、秘密/个人数据模式及核心 Python 语法。它们**不能**证明前端功能、Bank 迁移、MCP 宿主送达或 GitHub Release 已完成。

按本次改动的组件补跑对应全套测试和生产构建，例如 Host Adapter 的 `unittest discover`、Console 的 `npm test`、`tsc --noEmit` 和 `npm run build`；API/Controller/Status 的测试也应在变更到它们时执行。Web 交互改动还要在桌面和手机视口检查截图、点击、滚动、空态和浏览器错误。记录测试命令、数量、时间、失败/跳过范围，不把开发仓库的通过结果代替发行仓库的验收。

## 发布后的回读

核对 PR/分支/Tag/Release 的实际 URL 与 commit SHA，下载或克隆公开产物后重复脱敏扫描和最小启动/读取测试。更新 [发布记录](RELEASE-LEDGER.md)，分别写清“本地准备、PR 提交、PR 合并、Tag、GitHub Release”的状态与日期；未发生的阶段留空或标记未执行。
