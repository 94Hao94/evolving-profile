# Evolving Profile 5.0.0

发布日期：2026-10-02
状态：本地发布包已准备，PR 待创建

## 解决的问题

EP 4.0 能够记录和检索用户记忆，但 Agent 在执行任务时产生的失败、修复、效率和验证经验缺少独立的生命周期。5.0 将这类过程记忆从用户记忆中分离出来，并在链路页上把用户记忆、智能体过程记忆、外部 RAG 的调用和送达状态完整呈现。

## 本次变更

- 增加 Agent Process Memory 数据平面及 P0-P4 成熟度层级。
- 增加 Agent Recall/Research/Observe/Guidance/Evaluation/Writeback 路由和回执。
- 增加完整执行拓扑、React Flow + ELK 布局、分支/汇聚、节点详情和每节点计数。
- 修复 Prompt 详情加载期间被误显示为空、父节点总数复制到子节点和状态服务超时时无法回读本地 Hook 回执的问题。
- 增加智能体过程记忆逐模块开关，保留旧数据并避免禁用检索后仍注入。
- 补齐英文默认、多语言回退、日期/状态/错误和节点标签的本地化检查。
- 保持 EP Bank 与外部 RAG 隔离，保留 Embedding/Rerank/RRF/索引签名/JEV/Provider fallback 配置。
- 增加唯一真相源清单和本次链路截图；不打包个人 Bank、Prompt、日志、缓存和密钥。

## 升级与回退

升级前备份 Bank、Guidance Registry、runtime settings、backup settings 和审计回执。4.0 的用户记忆模型和旧工具名继续兼容。若 Embedding、维度或模型路径改变，先按索引签名重建外部 RAG。回退时恢复上一版本分支和配置快照；Agent Process Memory 可按策略保留或移除。

## 已知边界

- 回执可以证明调用、返回、送达和原文回读，不能在宿主没有 answer-use 记录时证明模型最终采用了某候选。
- 情景摘要、过程模式和 RAG 候选都不是原始事实，关键结论仍需回读来源。
- JEV 默认关闭，调用失败时由规则和未知状态托底。
- 本文件记录的是本地包和 PR 准备状态，不代表 PR 已合并、Tag 已创建或 GitHub Release 已发布。
- `npm ci` 报告 3 个上游依赖审计项（1 low、1 moderate、1 critical）；本次未执行可能产生破坏性升级的 `npm audit fix --force`，应在独立依赖升级 PR 中处理。

## 验证

| 范围 | 命令或读回 | 结果 |
| --- | --- | --- |
| 发布预检 | `python3 scripts/test_release_preflight.py`、`python3 scripts/release-preflight.py --json` | 通过；版本、分支、README、NOTICE、CHANGELOG 一致 |
| 脱敏包 | `./scripts/verify-package.sh` | 通过；无个人 Bank、姓名、密钥或个人路径命中 |
| Console | `npm test`、`npm run build`、`npm run i18n:check` | 23 个测试文件、146 项通过；多语言检查通过；生产构建通过（6 个运行时动态路径追踪警告，无构建错误） |
| Python | Host Adapter、Controller、Guidance、Status | 636 passed、2 skipped、35 subtests passed；2 个跳过是发行包未携带的私有回滚演练脚本 |
| API | `api/tests/test_hermes_templates_import.py` | 10 passed；1 个 sentence-transformers 兼容性 FutureWarning |
| 浏览器 | 已验证的实际链路截图与节点详情回执 | 采用脱敏链路图；本次公开包不包含本机 Prompt/回执，宿主实时 UI 仍需安装者在自己的环境复测 |

## GitHub 状态

- 仓库：`https://github.com/94Hao94/evolving-profile-2.2`
- 分支：`release/5.0.0`
- PR：待创建
- Tag：未创建
- Release：未发布

## 作者与致谢

发行署名沿用 `NOTICE.md` 的 CCY。Hindsight 和相关公开研究仅作为概念与工程背景致谢；提交者、仓库所有者和上游项目贡献者不因邮箱或代码引用自动混同。
