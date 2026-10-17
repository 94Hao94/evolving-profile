# EP5.1 分层证据审查：运行与验收边界

本功能不增加记忆维度、不替换旧摘要或原始对话。现行协议默认不变；新协议`hierarchical_review.v1`先用于影子结构及隔离评估，不能冒充旧协议穷举审查通过。

## 使用与状态

记忆库配置 → 情景摘要 → 审查协议。协议选择与既有运行模式/试点开关协同；未配置仍使用`segment_coverage.v1`。分层协议首版不支持enforced。

新协议的source_shadow不调用模型。辅助模式在缺少当前协议/模型的独立语义与回答效果资格证据时也不发请求，显示`semantic_readiness_unverified`。开启试点本身不授予额外额度。配置仅作用于明确选择的覆盖作业，不触发全部历史迁移。

已有证据分组可以可用，邻组仍未决；整个目标必须显示实际缺口。`scope_reviewed`只说明声明范围的来源、意图和已发现关系义务通过，不说明所有关系已穷举、外部成果真实或Agent已经采用。

四个读取视图仍为概览、要求、关系、原文。要求/原文较长时继续翻页；原文页验证raw_units、角色、原始记录哈希及当前来源/权限。候选、模型审查时读到原文、实际工具返回原文、宿主送达和回答采用分别计数。尚未整理好时仍可用原有获准原文入口。

提取模型可以只返回来源span别名及精确原句，宿主仅在该span内唯一逐字匹配时计算Unicode位置。重复原句必须由模型提供准确位置消歧；显式位置错误、缺少单边位置、原句不存在或空引文仍拒绝，不静默纠正模型的位置。定位成功只证明原句绑定，仍须独立逐意图复核；不会因此证明意图完整或外部成果真实。

新内部判断格式`attribution-scope-outcome.v1`分别记录原话/意图归属、对象/项目范围与未核验的外部成果。准确保留未明指代不等于已确认对象；助手说完成也不等于成果已核验。旧格式的accept=false仍拒绝；同一响应混用新旧判断契约也拒绝，不重新解释旧失败。

需要上下文时，在逐意图接受前读取同一冻结Session中相邻、获准的原始消息，保留角色、顺序、哈希、分页边界，不访问模型给出的路径。共享注册源限制最多2轮、3个来源单元，并再次检查完整请求容量和原预算；没有可用上下文不重复请求，有界补读后仍不明则保持未决。上下文读取计数是后台实际原文读取，不代表Agent已通过工具收到或最终采用。

独立分段可继续处理；失败段的原文支持候选仍可查看，但不标已审、不进入经审胶囊。有效归属条目与未决项目范围可以并存，相关组及祖先保持partial。上下文参与过的叶回执不能只凭主片段未变就跨代重绑；精确请求缓存仍可按原费用证明复用。

## 增量与费用

未变原文叶证据可以重新绑定，但保留原始模型请求及原费用回执，明确不是一次新HTTP调用。原句、角色、上下文、权限、模型或协议不同则不可复用。迟到纠正先使受影响结论失效；闭包不明时保守扩展至已选目标范围，不自动扫描全Bank。

所有重试、备用模型及未知费用仍进原账本。失败原作业和attempts不重置。胶囊缺页、意图缺口、容量或预算不足时保留partial/暂停，不能靠删掉困难案例取得通过。

## 隔离评估

`scripts/verify-hierarchical-review.py --preflight`在显式指定的baseline/state/session/output根下准备来源及冻结计划，零模型HTTP。它记录旧案例及结构化抽取的留出来源；任务类别和独立参考尚未审查时明确未核验。

真实执行还需要`--execute --case`、原`--grant-ledger`及`--expected-plan-sha256`。它不创建新grant、不改生产作业、不把评估结果直接写成生产资格。预估超过剩余额度就暂停；即使请求数下限合适，实际分段、输出和关系疑点仍可能产生额外成本。

评估必须分别保留逐断言语义、来源新鲜度、旧/新回答采用和实际成本。没有独立参考或宿主/回答证据时返回not_measured，不能让提炼模型自评代替。

## 资格记录与回滚

生产资格读取`context/coverage/hierarchical/qualification.json`，schema为`hierarchical-qualified-profile.v1`。必须绑定当前协议实现指纹、当前Provider标识指纹、输入/输出界限，以及包含完整case manifest和独立断言/回答证据的evaluation；资格校验不能只接受`semantic_ready:true`。文件指纹是本地完整性检查，不是独立签名或模型无误保证。

本次开发不预先制作通过资格，不自动打开辅助模式。未来真实评估通过后，资格只能由宿主审计结果形成，历史文本或模型输出不能写入该控制通道。新来源仍独立走权限、容量、预算和本代证据门，不能因模型资格通过就直接接受事实。

回滚选择现行协议并保留数据；旧结果必须仍符合来源/权限版本，不能复活过期指导。新产物存放在独立hierarchical目录，不覆盖legacy navigation。部署需分别核对磁盘代码、实际服务与原生MCP加载版本，接口200不等于视觉或模型质量验收。此功能不授权发布GitHub或修改云备份。

## v3 identity, constraint fidelity and bounded continuation

The optional hierarchical path uses the host-owned `source-selection.v3` wire;
the default daily protocol is unchanged. A model's `same_object` or `identity`
claim remains an open, source-bound hypothesis, even when it quotes an original
page or repeats a positive judgment during readback. Quote membership is not
identity entailment. Related records stay available; this is not a tighter
Recall relevance threshold. No authenticated identity proof is fabricated.

Reviewed summaries carry `summary_fidelity=not_certified_lossless`,
`constraint_use=original_source_required`, and `guidance_verified=false`.
Use the requirement's source locator before applying exact conditions,
negation, temporal limits or exclusive scope. The source response's
`record_source_complete_in_response` is response-specific: a final suffix page
is not the entire original record, and a returned page does not prove host
adoption, successful execution, or an external fact.

Full configured request envelopes are still measured against the existing
limits. The actual host response schema and a small explicit judgment header
replace repeated full relation-row examples; original text and canonical
records are not truncated. If even one bounded merge cannot fit,
`capacity_recovery` identifies its stage, measured bytes, input bound, all
records unexecuted in that invocation, and the original-read/continuation
route. No oversized model request is sent and no complete target is claimed.

### 中文说明

新 v3 线协议下，“同一对象”只作为待核实假设保留，不能凭模型判断和引文存在就
自动合并项目；后续回读再次说“支持”也不能提升权限。此限制不删除弱相关候选，
也不影响现有 Recall 相关度设置。当前没有独立身份凭证时，真实相同对象也可能
保持未决，调用方需围绕原文继续调查，不能假造已认证关系。

摘要经过归属审查，不代表精确条件无损。要求/原文视图保留原文定位、游标及
单次响应完整性标记；涉及“只限、每一项、最重要、尚未、某个时间或项目”等
执行条件，应以原文为准，而非从摘要猜测。该保护没有依赖这些示例词的词表。

容量保护不提高上限、不缩小来源范围。暂停回执列出本次调用中全部未执行记录，
而非只列超大的那一条。所有失败和真实调用用量保留，不通过重置次数或改判旧回执
取得全绿。上述安全修复不自动开启日常辅助模式；仍需当前协议、模型和回答效果
的独立资格证据，不能把隔离样本闭环或原文可读说成全历史语义验收。
