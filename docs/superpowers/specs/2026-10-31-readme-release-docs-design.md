# EP 5.1.4 README 与部署文档校准设计

## 目标

让新读者从 README 首屏找到中文入口、理解 EP 使用前后的具体收益，并能按当前 5.1.4 源码完成本机部署、健康检查、宿主接入、升级、备份和回退。文档必须把 Claude Desktop（普通 Chat/Cowork）与 Claude Code（CLI/桌面 Code 页）明确分开。

## 范围

- 根 `VERSION` 作为唯一产品版本源；在 README、部署文档和发布链接中统一引用 5.1.4。
- 重审 `README.md` 与 `README-中文.md` 的首屏、能力叙述、对比示例、快速开始、宿主矩阵、限制和链接。
- 校准 `docs/DEPLOYMENT.md` 与 `docs/DEPLOYMENT-中文.md` 的版本、安装、启动、验收、备份/恢复和升级回退说明。
- 修正会直接误导读者的相关 Agent/宿主文档旧版本指引。

## 非目标

- 不修改记忆数据库、API 业务逻辑、宿主插件行为或模型选择。
- 不把示例对话写成真实基准或保证；明确标注为 illustrative。
- 不把朋友仓库的 PR 当成个人仓库的直推，也不直接写入朋友主分支。

## 约束与验收

- 英文 README 标题下第一行提供 `README-中文.md` 链接，中文 README 保留 English 链接。
- 所有普通桌面 Chat 文案使用 `Claude Desktop`；只有实际 Code 工作区使用 `Claude Code desktop — Code tab`，并在文档中解释两者不是同一入口。
- 安装命令、端口、健康检查和备份命令必须与仓库当前脚本一致。
- 不再出现 README/部署文档中的 `release/5.1.0` 或 `v5.1.2-rc.1` 作为当前安装指引。
- 预检脚本、链接扫描、文档版本扫描和现有针对性测试全部通过。
