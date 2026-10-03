# 发布记录

这里记录已核实的发布阶段，不代替各版本 CHANGELOG。状态变更时更新本页，保持 PR、Tag 和 GitHub Release 分开。

| 产品版本 | 已核实状态 | 证据 | 署名边界 |
| --- | --- | --- | --- |
| 3.0.0 | 发行包已在 fork 的 `release/3.0.0` 分支提交；向上游 `main` 的 PR #1 于 2026-09-24 合并。截至 2026-09-26，上游未列出 Tag 或 GitHub Release。 | [PR #1](https://github.com/94Hao94/evolving-profile/pull/1)，合并提交 `545c03c`；本地发行分支提交 `2186354` | NOTICE 署名 CCY；Git 历史另含 `apple` 和 `zouhao` 提交身份，不能仅凭邮箱确定公开贡献署名。 |
| 4.0.0 | 本地发行分支 `release/4.0.0` 已推送到 fork，已向上游提交 PR #2；尚未合并、打 Tag 或创建 GitHub Release。 | 本地提交 `9490f1b`；[PR #2](https://github.com/94Hao94/evolving-profile/pull/2)；预检通过；Host 295（含 2 个可选回滚测试跳过）、Controller 179、Guidance 73、Console 144、生产构建通过 | 继续沿用 NOTICE 的 CCY 发行署名；Git 提交身份仍不自动等于公开贡献署名。 |
| 5.0.0 | 发行分支已推送到 fork，并已向上游提交 PR #3；尚未合并、打 Tag 或创建 GitHub Release。 | 当前分支 `release/5.0.0`；发布提交 `461ce97`，最新文档/审计提交 `84e767a`；[PR #3](https://github.com/94Hao94/evolving-profile/pull/3)；发布说明 [`RELEASE-NOTES-5.0.0.md`](RELEASE-NOTES-5.0.0.md)；链路配图 [`assets/flow-topology-5.0.jpg`](assets/flow-topology-5.0.jpg)及 README 视觉资产；门禁：636 Python passed、2 skipped、35 subtests，Console 146 passed，API 10 passed，构建和脱敏扫描通过 | 继续沿用 NOTICE 的 CCY 发行署名；Agent Process Memory、链路观测和 5.0 文档是本次 EP 贡献，不将 Hindsight 或其他上游项目写成 EP 代码贡献者。 |

下一次发布前先运行 `python3 scripts/release-preflight.py --json`，用当次 GitHub 读回修正仓库 URL、PR 状态和贡献者记录，不沿用旧快照。
