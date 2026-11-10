# Hindsight 三路差分召回验证与循环修复 SPEC

- **版本**：1.0
- **日期**：2026-08-30
- **状态**：用户已授权按本 SPEC 执行
- **适用范围**：本机 Hindsight 的“找全相关记忆、拒绝完全无关记忆、真实注入、回答利用、9998 可视链路”质量修复
- **独立性声明**：本文是一次独立的验证与修复执行规范，**不属于、不修改、也不依赖**《Hindsight Agent Memory OS SPEC》。新会话只读本文即可继续本任务。

---

## 1. 本次任务要解决什么

本次任务不是把“注入条数”调大，也不是为某一句已知问题补特例，而是验证并修复以下能力：

1. 对同一真实问题，Hindsight 能找出 Bank 中所有对回答有实质帮助的当前事实、历史事实和关联关系；
2. 相关内容多时允许多注入、分层压缩或提供可展开证据，不以固定条数截断；
3. 完全无关内容不得注入；边界相关内容必须有可解释的保留或拒绝理由；
4. 生产 Hook 实际送进 Agent 上下文的内容足以支持答案，而不是只在后台“检索到”；
5. 在关闭 Agent 原生长期 Memory 后，Hindsight-only 回答对跨会话事实的覆盖不低于“当前上下文＋原生 Memory”，并尽量接近 Bank 中实际存在的完整答案；
6. Controller、Hook receipt、日志、实际注入和 `http://127.0.0.1:9998/` 的数量、内容与路径一致；
7. 修复必须能迁移到不同措辞、不同实体、不同项目和不同任务类型，不能只对测试题有效。

“完成”只表示本文定义的验收集全部通过，不表示数学上证明未来所有自然语言问题永不失败。

## 2. 不做什么

- 不用 Hindsight 替代当前会话中尚未写入 Bank 的即时上下文；
- 不把 Context、任务状态卡、后台稍后到达的结果或测试 gold 伪装成“本次 Hindsight 实际注入”；
- 不用固定注入条数、固定关键词表、已知记录 ID、完整测试句或已知时间戳解决问题；
- 不因召回条数为 0 就自动判错：真正不需要长期记忆的题允许 0，但必须由独立 gold 证明；
- 不因召回条数大于 0 就自动判对：错、旧、重复或无关内容仍是失败；
- 不把服务健康、接口 200、单测通过或状态页有节点等同于用户可用；
- 不把 Bank 中不存在的真实世界事实算作召回漏失。

## 3. 方法依据

本 SPEC 采用以下可验证原则，而不是只看一个综合分：

- [LongMemEval](https://arxiv.org/abs/2410.10813) 将长期记忆能力拆为信息提取、跨会话推理、时间推理、知识更新和拒答；本测试矩阵必须覆盖这些能力。
- [RAGChecker](https://arxiv.org/abs/2408.08067) 将检索与生成分开诊断；因此本文区分“未检索、检索未注入、注入未利用、页面投影错误”。
- [NIST TREC relevance judgments](https://trec.nist.gov/data/reljudge_eng.html) 使用多路结果池形成相关性判断；本文的 Bank gold 也必须汇合多种互补检索，而不能把单一向量搜索当穷尽结果。
- [NIST 对 pooling 局限的研究](https://www.nist.gov/publications/bias-and-limits-pooling-large-collections) 指出固定深度池会漏掉不含题面词的相关文档；因此不得用固定 top-k 证明 Bank 已找全。

## 4. 三路必须相互独立

每个测试问题都建立 A、B、C 三路。禁止用 C 的返回倒推或删改 gold。

### 4.1 A 路：Context＋Native Memory

目的：得到该 Agent 在不依赖 Hindsight 时实际可形成的最好答案。

输入允许包含：

- 当前会话仍可见上下文；
- 上下文压缩摘要；
- Codex/Hermes 等宿主的原生长期 Memory；
- 当前任务有权读取的当前文件或项目状态。

输出必须包括：

- `a_answer`：完整回答；
- `a_claims`：回答中的原子命题；
- `a_sources`：每条命题来自当前上下文、压缩摘要、原生 Memory 还是当前文件；
- `a_known_gaps`：因上下文压缩、来源缺失或时间不确定造成的已知缺口。

A 路是现实基线，不是假定完整的 gold。

### 4.2 B 路：Bank Exhaustive

目的：得到“当前获准 Bank 内实际存在的信息上限”。

B 路必须绕过生产 Hook、Query Controller、Working Set 去重、融合阈值和最终注入准入，直接读取 Bank，并至少运行以下互补通道：

1. 语义检索；
2. 关键词、短语、别名和词干检索；
3. 时间范围、版本、最新/历史状态检索；
4. 实体规范名、别名、共指和关系检索；
5. 图谱邻边和多跳关系展开；
6. 星座/相关记忆关联展开；
7. 世界事实、经历、观察和心智模型的分类型检索；
8. 来源证据、权威等级、纠正、冲突、替代和失效关系；
9. 分页直到边际新增相关命题收敛，而不是只取固定 top-k；
10. 对多路结果并池、去重和逐条裁决。

每次 B 路还必须做完整性挑战：

- 增加至少一种与题面词不同的改写查询；
- 从已找到实体和关系反向展开；
- 检查是否存在只被一种通道找到的相关命题；
- 继续一轮扩展后若仍出现新必需命题，则不得宣称收敛；
- 保留未裁决候选，不能默认未进入池的内容无关。

输出必须包括：

- `b_answer`；
- `b_claims`；
- `retrieval_runs`；
- `bank_record_ids`；
- `graph_edges`、`constellation_links`、`entity_aliases`；
- `pagination_receipts`；
- `completeness_challenge`；
- `b_limitations`。

B 路只代表 Bank 内上限，不代表 Bank 外的绝对真相。

### 4.3 C 路：Production Hindsight

目的：记录用户实际使用时生产链路做了什么。

C 路必须使用真实提示词和生产等价入口，记录：

- Controller 对问题的理解、路由和检索分面；
- 每个分面的候选、分数、来源、分页和耗时；
- 图谱、星座、实体、观察、心智模型是否被使用；
- 候选去重、冲突/时间仲裁和每条拒绝原因；
- Controller 最终准入；
- Hook **实际注入**的逐条文本、Bank ID、Token、顺序和 receipt；
- Agent 是否在答案中明确引用、可能使用、无法判断或明确忽略；
- 9998 的节点、数量、详情和状态。

仅被检索或留在后台的候选不计入实际注入。

### 4.4 C-answer：Hindsight-only 回答

使用独立、无残留的 Agent 进程：

- 关闭原生长期 Memory 和历史索引；
- 只保留理解本轮问题所必需的当前上下文；
- 只提供 C 路真实注入包，不提供 A/B 答案、gold 或评审解释；
- 生成 `c_answer`，再揭示 gold 评分。

这样才能判断 Hindsight 是否真正能承担跨任务长期记忆，而不是被当前上下文或 `MEMORY.md` 托底。

## 5. Gold 不是简单并集

先把 A 和 B 拆为原子命题，再由来源、时间和任务意图裁决。每条命题最少包含：

```json
{
  "claim_id": "stable-id",
  "statement": "可独立核验的命题",
  "role": "required|supporting|history_only|exclude",
  "temporal_scope": "当前或历史时间范围",
  "entities": [],
  "relations": [],
  "source_authority": "current_user|current_file|bank_evidence|derived",
  "supersedes": [],
  "contradicts": [],
  "a_covered": false,
  "b_covered": true,
  "bank_handles": [],
  "c_retrieved": false,
  "c_admitted": false,
  "c_injected": false,
  "c_answer_used": false,
  "adjudication_reason": ""
}
```

裁决规则：

- 当前用户明确纠正和当前权威文件优先于旧记忆；
- “当前是什么”应排除已被替代旧状态；
- “如何演进/更新履历”必须保留旧状态及其替代关系；
- 重复记录不能虚增覆盖率；
- 只有能改变答案事实、行动、约束、风险或解释的内容才算相关；
- A 与 B 冲突时保留冲突本身及裁决理由，不为了让 C 通过而删命题。

## 6. 逐层指标

每题必须报告：

| 指标 | 定义 |
|---|---|
| Bank completeness | B 路完整性挑战是否收敛，关键通道、分页和关联边是否穷尽 |
| Retrieval recall | C 候选覆盖的 required claims / gold required claims |
| Injection recall | C 实际注入覆盖的 required claims / gold required claims |
| Injection precision | C 实际注入中相关且适用的 claims / C 实际注入 claims |
| Relation closure | 时间、实体、因果、任务、文件、图谱与星座必需边的覆盖 |
| Answer parity | C-answer 相对 gold、A-answer、B-answer 的必需事实和任务结果差异 |
| Trace fidelity | Controller、Hook receipt、日志、Bank ID、9998 数量与详情的一致性 |
| Latency | 规划、检索、展开、融合、准入、注入、回答和页面投影耗时 |

条数不是指标。若 required claims 很多，可动态增加正文 Token、压缩同类事实、分层组织或返回 expansion handle；但尚未进入本轮 Agent 上下文的内容不能计入 injection recall。

## 7. 失败定位表

| 现象 | 首查层 |
|---|---|
| B 有，C 候选没有 | 问题理解、查询分面、Bank scope、分页、语义/关键词、实体解析、图谱/星座展开 |
| C 候选有，Controller 未准入 | 融合、相关性、时间/来源仲裁、冲突、预算 |
| Controller 准入，Hook 未注入 | 双层准入、序列化、Token 包装、超时、receipt |
| Hook 注入，C-answer 未利用 | 注入包结构、证据可读性、重复稀释、归因、模型注意力 |
| 真实注入与 9998 不一致 | trace 关联、owner-turn 合并、状态投影、缓存、前端呈现 |
| 同题好、改写题坏 | 关键词特例或测试泄漏导致过拟合 |
| 相关内容少而无关内容多 | 查询意图/实体错误、粗粒度摘要污染、错误图扩展或排序 |
| 合理应为 0 却大量注入 | abstention/当前来源优先策略失效 |

## 8. 不可跳过的红绿循环

每一题严格按下列状态机推进：

`建立 A → 建立 B → 裁决 gold → 运行 C → 生成 C-answer → 三路差分 → 定位失败层 → 写红测试 → 最小泛化修复 → 同题复测 → 两道迁移题 → 一道无关负例 → 一道封存题 → 9998 视觉/DOM核对 → 记录通过`

约束：

1. 红测试必须在修改前复现失败；
2. 修复应作用于失败机制，禁止按题目字符串、Bank ID 或已知答案打补丁；
3. 同题未通过前不得用新题掩盖；
4. 同题通过但任一迁移题、负例或封存题失败，仍保持失败；
5. 每次修复后运行既有回归，发现退化立即定位；
6. 所有实际运行使用唯一 `case_id`、`execution_id` 和测试 generation；
7. 测试提示、gold、答案和评审不得进入生产记忆写入链路；
8. 非确定性步骤至少以不同顺序复跑三次，不能只留最好结果。

## 9. 防过拟合与泛化

测试分为：

- **dev**：允许看差分并修改代码；
- **paraphrase/transfer**：同一信息需求换措辞、实体、项目、日期、文件类型；
- **negative control**：相似表面词但不应注入目标记忆；
- **sealed holdout**：修复前封存问题与 gold，开发过程不可读取。

每个修复至少满足：

- 原题红转绿；
- 2 个迁移题通过；
- 1 个负例仍能拒绝无关内容；
- 1 个未见题通过；
- 现有已通过类别无回退。

## 10. 当前验收矩阵

本轮至少完成 20 个全证据真实问题，其中至少 5 个为 sealed holdout。必须覆盖：

1. 开放盘点/更新履历；
2. 跨任务接管；
3. 关联 Office/文件修改的全局联动；
4. 防止同类问题复发；
5. 实体同一性、别名和图谱关系；
6. 时间演进、知识更新和旧口径替代；
7. 来源追溯和权威仲裁；
8. 观察与心智模型；
9. 当前上下文与长期记忆协同；
10. 冲突策略与当前状态；
11. 星座/图谱多跳闭包；
12. 合理的零注入与拒答。

20 题是当前发布的最低验收集，不是宣称覆盖所有未来问题。任何一题全证据门失败，完成度都不是 100%。

## 11. 9998 状态页验收

每题必须用真实浏览器检查所选记录，必要时逐个点击链路卡片。至少验证：

- 左侧记录与真实 owner turn 一一对应，重复提问不会被错误合并；
- 实际链路完整，不因来源优先、工作集、跳过 Hindsight 或超时而无解释地断线；
- 检索候选、最终准入、实际注入、拒绝、后续使用分别显示，不混为一谈；
- “实际注入 N 条”可直接展开看到 N 条内容、Bank ID、来源、为什么进入；
- 0 条时显示是“合理无需长期记忆、当前来源覆盖、候选被拒、预算暂缓、超时/故障”中的哪一种；
- Controller、Hook receipt、日志和页面数字一致；
- 卡片文案能回答“做了什么、为什么做、发现什么、为何保留/拒绝、是否影响回答”；
- 箭头、节点、动态/静态状态、遮挡、溢出、缩放和滚动无视觉歧义；
- 截图证据与 DOM/接口证据同时留存，不能只靠肉眼口述。

## 12. 验证器的硬门

验证器必须读取 append-only manifest，并且只在以下全部满足时退出码为 0：

- 每题五个证据接口齐全：A、B、C、C-answer、9998 visual；
- `bank_completeness`、`retrieval_recall`、`injection_recall`、`injection_precision`、`relation_closure`、`answer_parity`、`trace_fidelity` 全通过；
- 失败题存在修改前红证据、修改后同题绿证据；
- 每个修复关联 2 个迁移题、1 个负例和 1 个封存题；
- 至少 20 个题全部通过、至少 5 个封存题通过、类别覆盖完整；
- 全量单测、生产等价 Hook、健康、重启恢复和回滚探针通过；
- 所有 evidence 路径存在，hash 与 manifest 一致；
- 状态页截图/DOM 检查和真实 receipt 一致。

只要验证器为非零，任务状态必须保持 `in_progress`。实施者不能用“已完成若干修复”“服务健康”“看起来正常”手工覆盖验证器。

## 13. 证据目录与文件契约

```text
hindsight-memory-os/
├── HINDSIGHT-THREE-WAY-RECALL-VALIDATION-AND-REPAIR-SPEC-2026-08-30.md
├── tools/hindsight_completion_validator.py
├── tests/test_hindsight_completion_validator.py
└── evidence/three-way-recall/
    ├── manifest.json
    ├── cases/<case_id>/
    │   ├── a-context-native.json
    │   ├── b-bank-exhaustive.json
    │   ├── gold-claims.json
    │   ├── c-production-trace.json
    │   ├── c-hindsight-only-answer.json
    │   ├── diff.json
    │   ├── red-before.json
    │   ├── green-after.json
    │   ├── status-page.png
    │   └── status-page-dom.json
    └── validator-result.json
```

不得用旧的泛化测试报告替代这些新证据；已有 20/40 题回放只有在补齐 A/B/C 独立证据后才可纳入。

## 14. 首个真实失败样本

首题使用用户在 2026-08-30 21:09 左右提出的真实问题：重复确认“以 Bank 全面答案为基准，检查现有 Hindsight 注入是否称职并循环修复”的要求。现网页面表现为 Controller 已完成多个分面、融合已有候选，但 Hook 实际注入为 0。

该样本必须先回答：

1. B 路在 Bank 中能找到哪些与该要求和 Hindsight 更新/修复相关的必需命题；
2. C 的候选中哪些覆盖这些命题；
3. 候选为何在 Working Set 去重、当前状态优先、融合、预算或 Hook 准入阶段全部消失；
4. 0 注入究竟是合理的当前上下文覆盖，还是使 Hindsight-only 无法回答的错误抑制；
5. 修复后同题、改写题、不同项目迁移题和无关负例是否都通过；
6. 9998 是否准确解释从候选到实际注入的差异。

## 15. 新会话接管步骤

新会话无需读取旧架构 SPEC 或依赖本次聊天。只需：

1. 完整阅读本文；
2. 运行验证器，确认当前为非零；
3. 从 manifest 中第一个失败 case 继续；若为空，从第 14 节首题开始；
4. 建立 A/B/gold 后再运行 C，禁止先看 C 再写标准；
5. 复现红测试，定位失败层，做最小泛化修复；
6. 跑同题、迁移题、负例、封存题、回归和 9998 视觉；
7. 证据齐全后由验证器自动计入；
8. 验证器退出码非零时不得宣称完成或停止在“阶段性完成”。

## 16. 最终交付

最终必须交付：

- 20 个全证据 case 及 5 个 sealed holdout；
- A/B/C 和 C-answer 的逐题差分；
- 每个缺陷的根因、红测试、泛化修复和回归证据；
- Bank 全面答案相对 A 的新增价值，以及 C-answer 相对 A/B 的差距；
- 9998 视觉与 receipt 一致性证据；
- 性能、健康、重启、回滚结果；
- 验证器退出码 0 的最终报告。

在这些结果出现前，本任务仍是执行中。
