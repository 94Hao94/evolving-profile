# Windows接入准备，不是原生运行认证

[English](WINDOWS.md) · [总说明](README-中文.md)

Windows原生、Windows到WSL、Windows到远端分别配置和验收。不能混用路径，不能默认
localhost转发、映射盘锁或桌面程序PATH可用。本轮准备文件不等于已运行Windows执行器。

已准备有界、只读的 Windows 标准卸载登记元信息识别：只读名称、版本、安装目录，
最多512条、约2秒扫描预算。只有档案中的名称精确匹配才作为安装候选，不读取或执行
卸载命令，不读取对话；安装候选不证明MCP、Hook或桌面任务模式可用。便携版、MSIX、
重命名应用、权限不足或扫描未覆盖时仍可能为未知，不能据此判定客户端能力故障。
这一分支只有Mac上的合成元信息测试，尚未执行Windows原生登记读取。

已有Python3.11+和受信任源码时：

```powershell
./scripts/ep-host.ps1 list --json
./scripts/ep-host.ps1 discover --json
./scripts/ep-host.ps1 doctor --host workbuddy --json
./scripts/ep-host.ps1 config-preview --host workbuddy --json
```

启动器优先使用`api/.venv/Scripts/python.exe`，再尝试`py -3.11`、`python`，保留参数数组
和退出码；不自动安装系统依赖、客户端、服务或模型。doctor会将API、Controller、Worker、
本地模型和服务管理保留为未启动/未认证，不能把MCP工具列出当作整个后端已部署。

隔离测试可按[英文页](WINDOWS.md)创建`.host-test-venv`，安装测试专用锁定依赖，再运行
`scripts/verify-host-integrations.py`。手动触发的CI文件已准备，不会自动推送或运行。

实机重点：跨进程锁、超时/崩溃释放、文件占用、回退冲突、中文/空格路径、BOM/换行、
真实解释器和PowerShell启动。Windows共享锁保守串行化，不允许无锁降级。原生依赖有
障碍就报告障碍；WSL或远端通过不能冒充Windows原生通过。
