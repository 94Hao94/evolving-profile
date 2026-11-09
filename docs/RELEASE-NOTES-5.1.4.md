# Evolving Profile 5.1.4

## 这版解决什么

5.1.4 把 EP 的失败处理从“显示告警、等待人工”改为自动闭环：可恢复的失败由 AI 诊断并修复；来源不足、超预算或模型拒绝时生成 AI 报告并保留原文，不把报告误报成成功。

## 主要变化

- Repair API：来源指纹、目标版本、诊断预览、确认应用、取消和状态查询。
- 心智模型刷新：绕开重复失败的工具循环，使用受限长度 AI 修复器写入并回读。
- 队列一致性：worker 启动会为索引中缺失的 AI 任务补建 jobs，避免队列只存在于页面。
- 来源保护：超大来源信封自动扩展传输预算；原始来源不删除。
- AI 报告态：AI 报告表示已自动分析并给出原因、范围和下一步，不是人工审核，也不是成功发布。
- Console：问题行和详情面板都显示 AI 审查/AI 报告状态。

## 版本与兼容

- 产品版本：5.1.4，以根目录 VERSION 为准。
- API 组件版本仍单独维护；Console 包版本同步到 5.1.4。
- 既有 5.1.3 Claude Desktop / Claude CLI 接入保持不变。

## 验证

- API repair、HTTP 契约和 source-envelope 回归测试通过。
- Console operational overview 测试和 production build 通过。
- 本机 EP 回归检查通过：API、Controller、服务、备份回读、SHA256、Recall 和 failed operations 检查均通过。

## 边界

完整来源不可读或超出覆盖证明预算时，EP 自动生成 AI 报告并保留原文，不伪造摘要、不删除来源；来源恢复或分段预算升级后可继续自动处理。
