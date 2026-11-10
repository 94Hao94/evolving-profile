# Host preparation matrix

Registry revision: 2026-11-09-ep52-host-evidence

| ID | Host | Transports | Local MCP | HTTP MCP | Prompt hook | Session association | Receipt | Source readback | Native host |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codex | Codex | stdio / Streamable HTTP | host_verified | Documented | host_verified | host_verified | received | source_read | Verified |
| trae | Trae | stdio / SSE / Streamable HTTP | host_verified | Documented | host_verified | host_verified | received | source_read | Partial |
| claude_code_cli | Claude Code CLI | stdio / Streamable HTTP | Documented | Documented | Documented | parser_available | not_measured | Documented | Unverified |
| claude_code_desktop_local | Claude desktop · local Code | stdio / Streamable HTTP | Documented | Documented | Documented | parser_available | not_measured | Documented | Unverified |
| claude_desktop_chat | Claude Desktop · Chat | stdio | Documented | Unknown | Unknown | unverified | not_measured | Unknown | Unverified |
| hermes | Hermes | Unconfirmed | Unknown | Unknown | Unknown | unverified | not_measured | Unknown | Unverified |
| workbuddy | Tencent WorkBuddy | stdio / Streamable HTTP | Documented | Documented | host_verified | host_verified | received | source_read | Partial |
| doubao_work | Doubao Work | stdio / Streamable HTTP | Documented | Documented | Unknown | unverified | not_measured | Unknown | Unverified |
| generic_mcp | Other MCP client | stdio / SSE / Streamable HTTP | Unknown | Unknown | Unknown | unverified | not_measured | Unknown | Unverified |

Recipes and documentary evidence only; not native-host or Windows certification.
