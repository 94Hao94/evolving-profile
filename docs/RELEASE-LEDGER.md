# 发布记录

这里记录已核实的发布阶段，不代替各版本 CHANGELOG。状态变更时更新本页，保持 PR、Tag 和 GitHub Release 分开。

| 产品版本 | 已核实状态 | 证据 | 署名边界 |
| --- | --- | --- | --- |
| 3.0.0 | 发行包已在 fork 的 `release/3.0.0` 分支提交；向上游 `main` 的 PR #1 于 2026-09-24 合并。截至 2026-09-26，上游未列出 Tag 或 GitHub Release。 | [PR #1](https://github.com/94Hao94/evolving-profile/pull/1)，合并提交 `545c03c`；本地发行分支提交 `2186354` | NOTICE 署名 CCY；Git 历史另含 `apple` 和 `zouhao` 提交身份，不能仅凭邮箱确定公开贡献署名。 |
| 4.0.0 | 本地发行分支 `release/4.0.0` 已推送到 fork，已向上游提交 PR #2；尚未合并、打 Tag 或创建 GitHub Release。 | 本地提交 `9490f1b`；[PR #2](https://github.com/94Hao94/evolving-profile/pull/2)；预检通过；Host 295（含 2 个可选回滚测试跳过）、Controller 179、Guidance 73、Console 144、生产构建通过 | 继续沿用 NOTICE 的 CCY 发行署名；Git 提交身份仍不自动等于公开贡献署名。 |
| 5.0.0 | 发行分支已推送到 fork，并已向上游提交 PR #3；尚未合并、打 Tag 或创建 GitHub Release。 | 当前分支 `release/5.0.0`；发布提交 `461ce97`，最新文档/审计提交 `e7600f8`；[PR #3](https://github.com/94Hao94/evolving-profile/pull/3)；发布说明 [`RELEASE-NOTES-5.0.0.md`](RELEASE-NOTES-5.0.0.md)；链路配图 [`assets/flow-topology-5.0.jpg`](assets/flow-topology-5.0.jpg)及 README 视觉资产；门禁：636 Python passed、2 skipped、35 subtests，Console 146 passed，API 10 passed，构建和脱敏扫描通过 | 继续沿用 NOTICE 的 CCY 发行署名；Agent Process Memory、链路观测和 5.0 文档是本次 EP 贡献，不将 Hindsight 或其他上游项目写成 EP 代码贡献者。 |
| 5.1.0 | 个人 fork 的 `release/5.1.0` 已设为默认分支，并发布最新预发布版 `v5.1.0-rc.2`；同时已向上游提交 PR #4，尚未合并。README 已整理为完整产品介绍、部署指南和 Agent 安装提示词。 | 个人仓库 [`ccygod/evolving-profile-2.2`](https://github.com/ccygod/evolving-profile-2.2)；[最新预发布版 v5.1.0-rc.2](https://github.com/ccygod/evolving-profile-2.2/releases/tag/v5.1.0-rc.2)；[上游 PR #4](https://github.com/94Hao94/evolving-profile/pull/4)；[`CHANGELOG-5.1.md`](../CHANGELOG-5.1.md)；[`RELEASE-NOTES-5.1.0.md`](RELEASE-NOTES-5.1.0.md)；[`ep51-release-hero.png`](assets/ep51-release-hero.png)；预检、脱敏、166 Python、531 Console、TypeScript、生产构建和一键部署通过 | 沿用 NOTICE 的 CCY 发行署名；5.1 的 native review 仍明确区分非 HTTP provenance，不将未暴露的模型身份写成确定事实。依赖审计关键漏洞为 0，仍有 8 个高/中等级告警已记录。 |

下一次发布前先运行 `python3 scripts/release-preflight.py --json`，用当次 GitHub 读回修正仓库 URL、PR 状态和贡献者记录，不沿用旧快照。

### 2026-10-17：本地修复候选闭环，尚未外部发布

当前本地安装、回退与积压恢复记录见 [RELEASE-CLOSEOUT-5.1.md](RELEASE-CLOSEOUT-5.1.md)。
该记录与历史 RC 分开：本轮不推送、不移动 Tag、不创建新 Release、不合并上游。
只读回查时 [PR #4](https://github.com/94Hao94/evolving-profile/pull/4) 为 OPEN，
head `674c461641be0c019aae52088d3cddad77f90b6e`；不能据此声称当前本地工作已在远端。
此次代码/安装文档独立复核已通过；完整产品稳定性、全部历史语义质量与答案收益
不因候选测试通过而自动取得认证。下一次外部发布须再次读回实际提交与状态。

### 2026-10-13：5.1 后台写入热修复

本次仍为产品 5.1.0 的贡献分支热修复：结构化来源分块预算、持久失败隔离和后续
批次继续调度；迁移/回退与当次验证见 `RELEASE-NOTES-5.1.0.md`。个人发行分支及
上游 PR #4 使用同一修复提交。已有 `v5.1.0-rc.2` Tag/Release 不移动，不自动
合并朋友仓库的主分支；实际同步结果以当前 PR head 与远端分支 SHA 回读为准。

同日追加：精确原文选择器重试、完成回执绑定的隔离恢复、父子任务去重、当前 Bank
队列与主机调度状态分离，以及地图刷新显示修复。验证：1203 Python + 107 子测试、
229 项限定 API 测试、546 Console 测试、TypeScript/构建/脱敏检查，以及实际原操作
恢复和中英文/窄屏页面检查。该修复仍通过个人发行分支及 PR #4 同步；不改动 RC Tag，
不将 PR 更新冒称上游主分支已合并。
