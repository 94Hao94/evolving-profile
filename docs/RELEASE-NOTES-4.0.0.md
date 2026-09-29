# EP4.0 发布说明

## 本次贡献

本分支将 EP4.0 的已验证功能同步到脱敏发行仓库，并保留 3.0 的升级兼容和发布流程。

## 重点逻辑

EP4.0 先提供说明书、L0 导航和有界 Preference 候选，再由 Agent 根据完整任务决定是否使用 Recall、Research、Scenario Summary 或原文核验。外部 RAG、JEV 和高风险判断门均为可选模块，默认不会改变内部记忆链路。

## 验证范围

- Host Adapter、Controller、Guidance 单元测试；
- Console 测试、TypeScript 检查和生产构建；
- MCP 工具清单与旧名称兼容；
- Preference 候选预算与 Scenario Summary 路线；
- 9999 Console、API、Controller 和 Recovery 健康检查；
- 脱敏、秘密扫描和发行包结构预检。

具体数字和最终结果以本次发行预检回执为准。

