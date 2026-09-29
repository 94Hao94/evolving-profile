# Evolving Profile 4.0.0

发布日期：2026-09-29（贡献分支准备）

## 版本定位

EP4.0 在 3.0 的 Prompt 绑定、证据回读和多宿主审计基础上，扩展了情境理解、外部资料检索、模型路由、判断辅助和运行配置能力。

## 主要更新

### 1. 情境摘要与原始回溯

- 新增 Project / Session Scenario Summary；
- 支持 compact、standard、full 三种摘要层级；
- 情境摘要只作导航和背景补充，不替代事实证据；
- 根据缺口切换 `read_source`、Session 原始回放或 Project 范围回溯；
- 增加情境图谱、时间线、节点详情和来源边界说明。

### 2. Preference 路线统一

- 公开工具统一为 `get_preference`、`read_preference`、`read_preference_unit`；
- 旧工具名仅保留隐藏兼容映射；
- 按任务阶段自适应候选预算；
- 回执区分读取、送达和答案采用情况；
- 当前 Prompt 始终优先，偏好不能授权高风险动作。

### 3. 外部 RAG

- 新增独立外部 RAG 目录；
- 支持词法检索、向量检索、RRF 融合、Rerank 和结果门槛；
- RAG 与 EP Bank 隔离，关闭时不读取外部资料；
- 支持索引签名和模型更换后的重建提示；
- Console 支持目录选择和当前绑定模型显示。

### 4. 检索与判断模型

- Embedding、Rerank、RRF 分开配置；
- 支持本地模型与线上 API；
- 支持模型档案、路径检测、维度检查和绑定关系；
- Provider 支持主模型和 Fallback；
- JEV 作为可选判断器接入证据充分性、来源路由、故障归因和风险判断；
- JEV 默认关闭，失败时由规则和保守未知状态托底。

### 5. 备份与运行配置

- 支持备份目录选择；
- 支持每日、每周、每月计划；
- 支持保留天数、最大套数、最少成功套数和自动清理；
- 完整备份套按集合清理，并保留 SHA-256 校验；
- 本地备份与云端镜像策略分离；
- 版本信息统一由 `config/release-manifest.json` 管理。

### 6. 可视化与链路观测

- Preference、Scenario Summary 与 Facts/Experiences 使用统一星座图视觉；
- 统一节点尺寸、连线透明度和交互详情；
- 链路页继续区分候选、返回、送达、原文回读和答案使用未知；
- 统一新的工具名称和历史兼容映射。

## 兼容与迁移

- 3.0 的 Bank、L0/L1/L2 和历史数据模型继续保留；
- 旧 Preference 工具名仅作为兼容别名；
- RAG、JEV 默认关闭，不会改变已有 EP Bank 行为；
- 更换 Embedding 后需要检查索引签名并按提示重建；
- 升级前应备份 Bank、Guidance Registry、配置和审计回执。

## 已知边界

- EP 能确认工具返回和宿主传输，但不能直接证明 Agent 最终采用了某条偏好或历史；
- Scenario Summary 不是原始事实；关键结论仍需 `read_source` 或原始 Session 回放；
- JEV 不是 Recall/Research 替代品；
- 外部 RAG 不会自动成为 EP 长期记忆；
- 当前版本为贡献分支的 EP4.0 发行准备，不代表 GitHub Release 已完成。

