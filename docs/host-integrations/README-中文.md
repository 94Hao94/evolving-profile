# 宿主接入准备

[English](README.md) · [注册表生成的支持矩阵](MATRIX-中文.md) · [Windows](WINDOWS-中文.md) · [验收状态](ACCEPTANCE.md)

不同客户端共用EP核心，分别记录文档支持、配置、隔离协议检查和真实宿主证据。
当前Codex入口保留；新宿主采用只读工具权限，自动捕获默认关闭。准备不等于实机认证。

## 先检查，不改客户端

在已安装依赖的源码根目录运行：

```bash
api/.venv/bin/python scripts/ep-host.py discover --json
api/.venv/bin/python scripts/ep-host.py doctor --host workbuddy --json
api/.venv/bin/python scripts/ep-host.py guide --host doubao_work --locale zh-CN --json
api/.venv/bin/python scripts/ep-host.py config-preview --host workbuddy --json
```

识别只检查有界程序和配置元信息，不读取私人聊天。doctor不启动宿主或后台服务。
加`--probe`仅验证隔离EP进程的握手/工具目录，不查记忆、不调用模型，也不证明豆包或
WorkBuddy实际调用过。Windows入口见专项说明。

## 各宿主怎么接

- 豆包工作：官方文档支持HTTP/STDIO。本地任务优先准备本地STDIO命令、参数、环境变量；
  配置由界面管理，EP不编造本地配置路径。按需选择插件或使用说明；账号开放情况后续实测。
- WorkBuddy：按官方`.workbuddy/mcp.json`配方先生成预览，Hook和原文仍需真实客户端核对。
- Claude命令行、桌面本地Code和普通Chat分开，不能互相替代配置或生命周期证明。
- Hermes/其他MCP客户端先做显式能力核对；没有可靠格式或事件时保持未知，不自动接管捕获。

无Hook时规则/Skill仅增强触发，不能保证每轮使用。每轮需要轻量入口，不是机械调用所有
检索或原文工具；重要事实仍按证据缺口回读。宿主接收未知不显示0或成功。

## 配置、回退与界面

网页在记忆库配置的平行“宿主接入”标签展示能力，按钮自身反馈刷新/生成/检查结果。
准备模式不直接写客户端配置；应用和恢复按钮保持禁用，避免把准备当正式接入。
命令行操作员可用`config-preview --save-plan`保存计划，审阅目标/解释器/脚本/环境和
前版哈希后，显式传`config-apply --plan ... --expected-sha256 ... --confirm`应用。
恢复用保存回执和当前应用哈希，不能覆盖后续用户修改。格式不可靠时只提供导入片段。
JSON损坏、重复key、链接路径、无归属已有条目或并发编辑均拒绝；备份和可恢复回退保留。
不向计划填写原始密钥，其他MCP和Hook保持原样。详见[完整命令说明](README.md)。

## HTTP与Windows边界

已有API HTTP MCP与完整治理工具面不同。可选HTTP入口复用同一EP只读工具，通过认证范围
隔离stdio进程，不复制召回逻辑。默认不启动，即使环回也要求认证；不自动公开私人端口。
一个网关启动配置只服务同一EP数据owner，多宿主可以共享该owner；混用其他owner必须
独立配置核心，不能把进程隔离当Bank权限隔离。关闭/过期会话会释放归属记录与工作进程。
使用的FastMCP4.0.4协议栈已做本机隔离测试，不能由此宣称旧框架或所有平台都已认证。
Windows原生、WSL、远端单独记录；PowerShell入口不是完整后台服务安装器。

## 离线检查

```bash
api/.venv/bin/python scripts/verify-host-integrations.py
api/.venv/bin/python scripts/ep-host.py export-diagnostics --host workbuddy --json
```

合成来源与生产队列隔离，后台模型请求为0。诊断导出不附私人消息、认证头、URL令牌或
环境值。没有运行Windows执行器或真实宿主时如实留未测，不用模拟结果补齐。
