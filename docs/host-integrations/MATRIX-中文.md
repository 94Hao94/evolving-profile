# 宿主准备矩阵

注册表修订：08101a33425401e7b19f952581c0fd6cfed9dfb6c690f29ca7915e4dd6f58104

| ID | 宿主 | 传输类型 | 本地 MCP | HTTP MCP | 提问钩子 | 会话关联 | 回执 | 原文读取 | 宿主实测 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codex | Codex | stdio / streamable HTTP | 文档支持 | 文档支持 | 文档支持 | host_verified | received | source_read | 已实测 |
| trae | Trae | stdio / SSE / streamable HTTP | 文档支持 | 文档支持 | 未知 | host_verified | received | source_read | 已实测 |
| claude_code_cli | Claude Code 命令行 | stdio / Streamable HTTP | 文档支持 | 文档支持 | 文档支持 | parser_available | 未测量 | 文档支持 | 未实测 |
| claude_code_desktop_local | Claude 桌面端·本地 Code | stdio / Streamable HTTP | 文档支持 | 文档支持 | 文档支持 | parser_available | 未测量 | 文档支持 | 未实测 |
| claude_desktop_chat | Claude 桌面端·普通聊天 | stdio | 文档支持 | 未知 | 未知 | 未验证 | 未测量 | 未知 | 未实测 |
| hermes | Hermes | 未确认 | 未知 | 未知 | 未知 | 未验证 | 未测量 | 未知 | 未实测 |
| workbuddy | 腾讯 WorkBuddy | stdio / Streamable HTTP | 文档支持 | 文档支持 | 文档支持 | host_verified | received | source_read | 已实测 |
| doubao_work | 豆包工作任务 | stdio / Streamable HTTP | 文档支持 | 文档支持 | 未知 | 未验证 | 未测量 | 未知 | 未实测 |
| generic_mcp | 其他 MCP 客户端 | stdio / SSE / Streamable HTTP | 未知 | 未知 | 未知 | 未验证 | 未测量 | 未知 | 未实测 |

本表是配方与文档证据，不是当前宿主或 Windows 实测通过。
