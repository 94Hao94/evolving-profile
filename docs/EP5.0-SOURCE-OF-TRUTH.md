# EP 唯一真相源治理

EP 不应该让所有文件都互相复制并互相覆盖。每一类数据只保留一个可写权威，其他内容明确标记为投影、缓存、索引、回执或历史证据。

## 可以设为唯一真相源的对象

| 对象 | 唯一真相源 | 其他内容 |
|---|---|---|
| 产品版本与发布通道 | `config/release-manifest.json` | 运行目录中的发布副本、页面显示 |
| EP 运行配置 | `~/.evolving-profile/config/runtime-settings.json` | API 环境变量、页面状态、服务启动投影 |
| Guidance/Get Preference 策略 | `~/.evolving-profile/config/guidance-settings.json` | Hook 读取结果、页面展示 |
| 备份策略 | `~/.evolving-profile/config/backup-settings.json` | LaunchAgent plist、备份状态 |
| Provider 与模型活动配置 | runtime-settings 的 `providers.primary` | `evolving-profile-api.env` 只作为服务启动投影 |
| 用户记忆 | EP API PostgreSQL `memory_units` 及其关系表 | Recall/Research 候选、图谱和统计 |
| Agent 过程记忆 | `~/.evolving-profile/process-memory/records.json` | Console 图谱、统计卡片、候选策略视图 |
| 原始 Session/Conversation | `~/.codex/sessions` | 情境索引、摘要、历史候选报告 |
| 外部 RAG 原文 | `rag.root_path` 指向的资料目录 | 分块、向量索引、Rerank 结果 |

## 不应该升级为真相源的内容

- Recall/Research 返回的候选：只是待核验结果；
- L0、Scenario Summary 和 Context Index：只是导航或压缩投影；
- `records.json` 中的 `process_observation`：是过程观察，不是已验证能力；
- 候选过程策略：不能自动变成当前模型的硬规则；
- `runtime-settings.json` 的 API Key：是配置权威，但绝不应出现在 README、日志或历史摘要；
- LaunchAgent plist：只负责调度，不拥有备份策略；
- `console /api/evolving-profile/runtime`：只读运行投影，不反写配置或记忆；
- `docs/EP5.0-HISTORICAL-*.json`：只读历史候选和评测资料，不代表当前事实。

## 运行规则

1. 页面保存配置时只写对应的唯一真相源。
2. API 环境变量由配置应用流程生成，禁止人工把它当第二配置源。
3. 任何投影都必须保留来源和生成时间；可删除重建的索引不能覆盖原文。
4. 启动和发布前运行：

```bash
PYTHONPATH=host-adapter python3 host-adapter/source_of_truth_audit.py --json
```

5. 发现配置权威与运行投影不一致时，服务状态应标记为 `configuration_drift`，而不是静默选择其中一个。

本目录中的 `config/source-of-truth.json` 是这套治理的登记表；它本身只描述权威关系，不取代上述真正的数据源。
