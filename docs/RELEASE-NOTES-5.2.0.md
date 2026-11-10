# Evolving Profile 5.2.0 release notes

发布日期：2026-11-09（贡献发行版准备）
状态：个人 fork 发行分支准备；上游 PR 状态以 GitHub 实际读回为准。

## 本次发布内容

5.2.0 将来源绑定的个人记录作为 EP 的正式能力面：姓名、手机号、固定电话、邮箱、身份证号、车牌、单位、职务、地址和凭据引用按字段保存，人物关系必须有明确标签或结构化人物块支持。多人共现但没有明确关系时保持 `unbound`，不按出现顺序猜测。

同时发布最新的多路由历史检索回执、原文回读边界、个人记录早期写入、宿主传输矩阵和运行时一致性说明。公开包不含个人 Bank、转录、API Key、个人记录索引或本机运行回执。

## 宿主状态

| 宿主 | 当前状态 | 本版说明 |
| --- | --- | --- |
| Codex | `host_verified`：MCP stdio、prompt hook | HTTP、答案采用仍单独计量 |
| Trae | `host_verified`：MCP stdio、prompt hook、automatic capture | SSE/HTTP 档案已记录，原生全矩阵未完成 |
| WorkBuddy | `host_verified`：prompt hook、stop hook、automatic capture | 长驻旧 MCP 子进程需要重连后加载新适配器 |
| Claude Code CLI | 桥接与模拟宿主验证 | 不宣称真实 CLI 全任务验收 |
| Claude Desktop | 已有桥接/config 路径 | 真实客户端验收按既定范围暂缓 |
| Hermes / 通用 MCP | 共享契约与档案 | 原生生命周期和回执需逐宿主实测 |

## 验证边界

本次发布前至少执行：

- `python3 -m pytest -q host-adapter/test_personal_records.py`
- 个人记录的姓名过滤、固定电话、车牌、结构化人物块、多人不串线、拒绝误识别回归
- source/runtime/release 三份关键适配器哈希一致性检查
- 脱敏包扫描，确认没有个人记录、私有 transcript、API Key 和本机运行回执

本文件不把本地测试通过写成所有宿主都已通过，也不把存在配置写成真实客户端验收。

## 升级与回退

从旧版本升级时，先备份 Bank、Guidance、runtime settings、审计和宿主配置；再切换到 `release/5.2.0` 并重建匹配的 Console/API/Worker。已经运行的 MCP 子进程需要重新连接才能加载新的 personal-record adapter。回退时恢复旧分支和配置快照；原始个人记录和来源不会被公开包覆盖。
