# 发布记录

这里记录已核实的发布阶段，不代替各版本 CHANGELOG。状态变更时更新本页，保持 PR、Tag 和 GitHub Release 分开。

**本目录：5.1.2 RC1候选发行线。**以[VERSION](../VERSION)为产品版本权威，
新候选通道见发行清单；当前远端旧分支/下载包不代表它。新包验收见
[候选验收](CANDIDATE-ACCEPTANCE.md)，变化见[5.1.2说明](RELEASE-NOTES-5.1.2.md)。
下文5.1.1及更早的PR/提交均为历史发布证据，不是本候选已发布的证明。

### 2026-10-18：5.1.2 RC1候选发布跟踪

- 本轮已获得个人预发布和上游贡献发布授权，发行分支为`release/5.1.2-rc.1`，
  标签定位`v5.1.2-rc.1`。具体已发生状态在后续核实记录中补记，不以计划当结果。
- 个人候选入口：[RC1发布页](https://github.com/ccygod/evolving-profile-2.2/releases/tag/v5.1.2-rc.1)。
- 上游使用新的候选贡献PR，不覆盖或合并旧PR5。候选包含PR5尚未合并的5.1.1修复，
  维护者可自行决定合入顺序；本轮不关闭旧PR或替上游合并主分支。
- 已有本地验收和本轮发行树复核分别记账；新宿主/Windows真实验收仍未完成。

**上一条已记录补丁：5.1.1**。
维护分支沿用 `release/5.1.0`，不代表安装补丁仍为5.1.0。原 PR #4 已合并；
2026-10-18 的送达修复通过新的 [PR #5](https://github.com/94Hao94/evolving-profile/pull/5)
贡献，历史记录中的旧 PR 状态为当时快照，不覆盖当前核对结果。
旧 RC 标签/下载资产没有更新；要获取此补丁请使用当前发行分支或下方精确提交。

| 产品版本 | 已核实状态 | 证据 | 署名边界 |
| --- | --- | --- | --- |
| 3.0.0 | 发行包已在 fork 的 `release/3.0.0` 分支提交；向上游 `main` 的 PR #1 于 2026-09-24 合并。截至 2026-09-26，上游未列出 Tag 或 GitHub Release。 | [PR #1](https://github.com/94Hao94/evolving-profile/pull/1)，合并提交 `545c03c`；本地发行分支提交 `2186354` | NOTICE 署名 CCY；Git 历史另含 `apple` 和 `zouhao` 提交身份，不能仅凭邮箱确定公开贡献署名。 |
| 4.0.0 | 本地发行分支 `release/4.0.0` 已推送到 fork，已向上游提交 PR #2；尚未合并、打 Tag 或创建 GitHub Release。 | 本地提交 `9490f1b`；[PR #2](https://github.com/94Hao94/evolving-profile/pull/2)；预检通过；Host 295（含 2 个可选回滚测试跳过）、Controller 179、Guidance 73、Console 144、生产构建通过 | 继续沿用 NOTICE 的 CCY 发行署名；Git 提交身份仍不自动等于公开贡献署名。 |
| 5.0.0 | 发行分支已推送到 fork，并已向上游提交 PR #3；尚未合并、打 Tag 或创建 GitHub Release。 | 当前分支 `release/5.0.0`；发布提交 `461ce97`，最新文档/审计提交 `e7600f8`；[PR #3](https://github.com/94Hao94/evolving-profile/pull/3)；发布说明 [`RELEASE-NOTES-5.0.0.md`](RELEASE-NOTES-5.0.0.md)；链路配图 [`assets/flow-topology-5.0.jpg`](assets/flow-topology-5.0.jpg)及 README 视觉资产；门禁：636 Python passed、2 skipped、35 subtests，Console 146 passed，API 10 passed，构建和脱敏扫描通过 | 继续沿用 NOTICE 的 CCY 发行署名；Agent Process Memory、链路观测和 5.0 文档是本次 EP 贡献，不将 Hindsight 或其他上游项目写成 EP 代码贡献者。 |
| 5.1.0 | 2026-10-17 修复和产品文档已推送个人 `release/5.1.0`，现有上游 PR #4 已读回相同代码提交；PR 尚未合并。旧 `v5.1.0-rc.2` 仍是旧预发布产物，不包含本次分支更新；未创建新 Tag 或 Release。 | [个人发行分支](https://github.com/ccygod/evolving-profile-2.2/tree/release/5.1.0)；[代码提交 24f6be4](https://github.com/ccygod/evolving-profile-2.2/commit/24f6be4cabfee3b066893c427200c68eb0a33fd5)；[上游 PR #4](https://github.com/94Hao94/evolving-profile/pull/4)；[`CHANGELOG-5.1.md`](../CHANGELOG-5.1.md)；[`RELEASE-NOTES-5.1.0.md`](RELEASE-NOTES-5.1.0.md)；[`DEPENDENCY-RISKS.md`](DEPENDENCY-RISKS.md)。本次证据见下方日期记录。 | 沿用 NOTICE 的 CCY 发行署名；native review 区分非 HTTP 来源与未知模型身份。生产分类依赖审计 0；完整工作区 36 条，0 critical。不是全部依赖或全部历史语义的零风险认证。 |

### 2026-10-18：5.1.1 长会话送达回执修复

代码提交 [2b63ada](https://github.com/ccygod/evolving-profile-2.2/commit/2b63ada74867d49919b771a29a8d3ee3a0a0df3f)
及说明/构建标识提交 [9a175f7](https://github.com/ccygod/evolving-profile-2.2/commit/9a175f7)
已非强制推送个人 `release/5.1.0` 分支；新建
[上游 PR #5](https://github.com/94Hao94/evolving-profile/pull/5)，原 PR #4 已在
上游主分支合并提交 `218f45d` 中落地。PR #5 本次核对为 OPEN、尚未合并。
本页为后续发布证据补记，最终 head 以该分支及 PR 的实际读回为准。
产品仍为 **5.1.1**，构建标识为 `ep511-cross-date-host-delivery`；没有移动旧
RC 标签、创建 GitHub Release 或擅自合并主分支。

- 修复跨日期/归档长会话来源定位，核对授权范围与原生会话身份；使用有界
  尾部、流读取和选中轮次缓存，处理追加、部分来源与合法大行。缺失、歧义和
  超预算来源保持未知，不把候选数推断为接收数。
- Hook 已准备、真实返回和宿主接收分开统计；运行指导刷新偏好包进入对应节点。
  无证据的计划占位不冲掉已有接收小计；工具接收仍不证明最终回答采用。
- 本次发布前重新执行 Console：**94 文件 / 660 测试通过**、TypeScript、
  分发 Console 生产/standalone 构建、8 项发布预检测试，以及发行包结构与源码文本
  秘密/私人数据扫描。包内 **1741 个文件**在本地 Git 归档中逐项哈希一致。
  未变更 Python 后端逻辑，未冒用旧后端回归数字作为本次新测试。
- 前一修复验收已实际部署并点击旧 Prompt：中英文均确认一次指导调用返回5条、
  宿主收到5条；仅 Hook 准备的另一例保持未确认。原始截图和对话保留在私人审计目录，
  不上传公开。该观察不等于全部历史覆盖或回答收益基准。
- 保留手动校准的布局、记忆、配置、密钥、提炼队列和召回策略；Hindsight 来源声明
  与原许可保留。升级/回退及已知边界见 [补丁说明](RELEASE-NOTES-5.1.1.md)。

### 2026-10-17：5.1.1 部署与分宿主接入文档补丁

代码与文档提交 [5ee5043](https://github.com/ccygod/evolving-profile-2.2/commit/5ee50433070a482383fce1f86cbfcbe1ab400a40)
已推送个人发行分支；[上游 PR #4](https://github.com/94Hao94/evolving-profile/pull/4)
读回相同 SHA，OPEN、未合并。本页随后只追加核实记录，最终 head 以远端读回为准。
没有新 Tag/GitHub Release，没有移动旧 RC1/RC2，没有合并上游主分支。

中英文 README 入口、[完整部署](DEPLOYMENT-中文.md)、[分宿主配置](HOST-SETUP-中文.md)、
[Agent 安装提示词](AGENT-SETUP-中文.md)及[补丁说明](RELEASE-NOTES-5.1.1.md)已更新。
Codex、Claude Code CLI、桌面本地 Code、普通 Chat 分开；包含后台启动、配置归属、
网页建议、自动化边界、停止重启、备份与逐项验收。不把命令配方冒称已通过 Claude 原生全链路。

当次验证：Python **2146 passed、3 skipped、107 subtests**；Console **90文件/629项**；
TypeScript、干净 `npm ci` 和5.1.1生产/standalone构建通过。3项跳过为2个外部旧版回滚
集成和1个显式选择才执行的操作员本机状态审计；后者不能要求待发布源码擅自升级私人运行环境。
新隔离状态用例仍实际检查版本漂移，并证明不会改写旧状态。
文档34个Shell片段语法、6个JSON片段、102个本地链接检查通过；两个README各3个导航锚点、
30个本地目标经GitHub渲染检查无缺失。最小公开Controller配置在隔离状态实际启动并返回healthy，
stdio初始化列出34工具；0后台模型请求，不证明实际Provider连通或Claude宿主生命周期。
独立首次读者/代码审查的Important问题已修正，最终无Critical/Important未解决项。

这是公开发行包与文档补丁；未覆盖用户本机配置、密钥、Bank、Hook和运行服务。
安装器仍仅构建，Claude自动捕获、`.mcpb`包、云/SSH宿主及全部历史提炼没有因此新增认证。
此前[依赖风险](DEPENDENCY-RISKS.md)保持披露，不冒称全部风险清零。

下一次发布前先运行 `python3 scripts/release-preflight.py --json`，用当次 GitHub 读回修正仓库 URL、PR 状态和贡献者记录，不沿用旧快照。

### 2026-10-17：本地修复候选闭环，尚未外部发布

当前本地安装、回退与积压恢复记录见 [RELEASE-CLOSEOUT-5.1.md](RELEASE-CLOSEOUT-5.1.md)。
该记录与历史 RC 分开：本轮不推送、不移动 Tag、不创建新 Release、不合并上游。
只读回查时 [PR #4](https://github.com/94Hao94/evolving-profile/pull/4) 为 OPEN，
head `674c461641be0c019aae52088d3cddad77f90b6e`；不能据此声称当前本地工作已在远端。
此次代码/安装文档独立复核已通过；完整产品稳定性、全部历史语义质量与答案收益
不因候选测试通过而自动取得认证。下一次外部发布须再次读回实际提交与状态。

### 2026-10-17：随后授权的 RC 分支与贡献 PR 同步

这是上述“本地准备”之后单独获授权的外部同步，不改写此前的未发布记录。
代码提交 `24f6be4cabfee3b066893c427200c68eb0a33fd5` 已推送至个人发行分支，
GitHub PR #4 的 head 也已读回同一 SHA，状态 OPEN；后续本页的证据补记为文档提交。
旧 RC1/RC2 标签保持原提交，没有新建 Tag/Release，也没有合并上游 `main`。
需要本次更新的用户应选择发行分支或上述代码提交，而不是下载旧 RC2 资产。

本次独立审查覆盖新增变更及此前批准的冻结候选：一项旧版回滚测试的可选路径
检查缺陷经失败用例复现后修复，未实际执行历史回滚脚本。当前验证为：

- Python Host/Guidance/Controller/Status/发布脚本：**2142 passed、2 skipped、107 subtests**。
  两项跳过是未配置外部资产的历史 EP2.1 回滚集成，不算通过。
- Console：**90 文件、629 测试通过**；限定 API 回归 **56 通过**；TypeScript、
  SDK 与生产/standalone 构建通过。限定 API 测试不是全部外部集成认证。
- 正常 source-map、模板转义、选择器 AST 和真实 Typography 编译探针通过；
  生产分类审计 0、完整工作区 36 条（29 high、6 moderate、1 low、0 critical），
  四个残余 advisory 的范围与输入条件见风险文档，不隐去生成源码的已知问题。
- GitHub 实际下载的 **1719 个源码文件**与批准清单逐文件哈希一致，重新通过源码
  隐私扫描、结构预检和隔离的 stdio MCP `initialize` / `tools/list`：34 个工具，
  包含用户/智能体 Recall、Research、偏好、情景摘要和原文读取入口。
  该探针不调用模型，不证明宿主送达、回答采纳或全部历史提炼完成。
- 中英文 README 使用分别切换语言后的真实界面截图；去除私人 Prompt 侧栏，
  保留“送达未知”等实际状态。图像经过目视与原始像素一致性检查，非合成效果指标。

本地私人状态没有随发行包上传。分发默认路径、配置覆盖与合成测试数据已做可移植性
处理；私有服务磁盘代码核对不代表每个已运行 MCP 进程重新加载。当前记录是有边界
的 RC 贡献更新，不是所有宿主、平台、诊断语言或历史答案收益的稳定认证。

### 2026-10-18：5.1.1 指导工具参数防护与 Hindsight 来源声明

代码提交 `2b8149848cc090587abdb6b202de549f521257da` 已非强制推送个人
`release/5.1.0`，继续通过同一上游 PR #4 贡献；本页为后续证据补记，最终 head 以远端读回
为准。产品仍为 **5.1.1**，未移动旧 RC 标签、创建 Release 或合并上游主分支。

- 共享偏好入口在身份绑定前验证任务对象；刷新工具验证规范的单个失败事件和预算类型。
  错误结构返回 `-32602` 与可纠正的字段提示，不再抛出字符串 `.items` 异常。
  不猜测转换错误事件，不对无效参数递归补查，不把调用者任意字段名称反射进错误。
- 错误调用仍有独立失败 occurrence，但不伪造其 Prompt 绑定；同一 stdio 进程可接受
  后续正确重试。回归实际覆盖真假值的非对象参数、任务字段、事件结构、错误身份字段、
  未知字段不回显，以及拒绝前不触发身份查询。
- 本次 Guidance / Host Adapter / 核心 Recall Controller / 发布脚本回归
  **2068 passed、119 subtests passed、3 skipped**。跳过为两个未提供外部资产的历史
  EP2.1 回滚集成和一个需显式启用的操作员本机状态审计，不算通过。独立代码复核
  的 Important / Minor 问题均已闭合；生产检索阈值、记忆和密钥没有变动。
- 中英文 README 末尾明确“基于 Hindsight 开发”，并链接其原项目；NOTICE 同步
  说明上游基础与 EP 增量贡献。两份 README 经 GitHub Markdown 渲染，各 3 个锚点、
  32 个本地目标，无缺失。

运行文件更新与已有宿主连接重载是两个阶段：新启动的隔离 MCP 进程已实际通过
参数失败/重试验收，但不能因此声称所有正在运行的长连接均已重载。采用本补丁后
需重连已开启的 EP MCP，并核对实际入口构建回执；不需改 API Key 或重提炼历史。

### 2026-10-18：5.1.1 布局一致性与产品说明补丁

代码、文档与中英文真实截图提交为 `34404aed8fbe60c49f3e3301e9473fc172b32b31`，
已非强制推送至个人 `release/5.1.0` 分支；同一 head 随既有上游 PR #4 更新。
产品版本仍为 **5.1.1**，贡献分支名称不是产品版本号。本段证据补记为后续文档提交，
最终分支 head 应以 GitHub 实际读回为准。旧 RC 标签不移动，不新建 Release，不合并上游主分支。

- 将经实际 Chrome 校准的 39 个节点纳入统一画布坐标；布局保存为安装级共享配置，
  增加修订冲突检查与原子替换，保留上一个版本和浏览器旧草稿。不同语言的文字覆盖独立保存。
- 修复 SVG 字体重复缩放，以及本机地址规范化造成的真实保存 403。存储失败、损坏或
  并发冲突明确报错，不假装成功；遗留锁不按时间自动强删，需经确认的操作恢复。
- 当前补丁验证：Console **93 文件 / 642 测试通过**，TypeScript、公有分发与私人
  Console 的生产/standalone 构建通过；实际 Chrome 保存、全图/150%/200%、
  1280/768/390 像素宽度与中英文切换已检查。坐标采用独立数值比较，非只看缩略图。
  本次没有重新执行或冒用此前 Python/API 全量测试结果。
- README 用完整产品逻辑介绍而非版本更新列表；展开五维偏好、条件与例外、融合心智
  模型和用户/智能体记忆分类。新增中英文能力说明；分别切换语言后实拍链路截图，
  不含私人 Prompt 侧栏。截图来自同一历史回执，不是自然任务收益或召回率基准。
- 本地仅更新 Console 与布局设置；私人 API、Retain、Worker、模型密钥、记忆记录、
  历史提炼队列和云备份未随此补丁修改。布局一致性测试不构成所有未来故障零发生保证。

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
