"""Read-only MCP adapter for the locally active Multi-dimensional Preference registry."""
from __future__ import annotations

import json
import os
from pathlib import Path

from repository import GuidanceRepository
from selector import get_task_guidance
from receipts import record_mcp_stdout
from memory_usage_instructions import CORE_TEXT, LONG_TEXT, VERSION as INSTRUCTION_VERSION, content_sha256 as instruction_sha256, record as record_instruction
from runtime_recovery import refresh_runtime_guidance


GUIDANCE_INSTRUCTIONS = f"[{INSTRUCTION_VERSION} sha256={instruction_sha256()}]\n{CORE_TEXT}"


TASK_GUIDANCE_TOOL = {
    "name": "get_task_guidance",
    "description": "多维度偏好（Multi-dimensional Preference）路线。遇到实质任务时根据启动说明优先调用；传入用户原始消息、必要前文、任务阶段和约束，读取正式active偏好及其五维归类、融合定位层中的已有心智模型章节。只读；前台模型调用为0，不生成长期模型。返回完整条件、例外、来源、already_loaded_valid、deferred和分页游标。",
    "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
        "context_ref": {"type": "string"},
        "task": {"type": "object", "additionalProperties": False, "properties": {
            "objective": {"type": "string", "minLength": 1},
            "current_user_message":{"type":"string","description":"用户本轮原始消息；短句追问保持原文。"},
            "context_summary":{"type":"string","maxLength":12000,"description":"仅传解开指代所需的前文摘要，不改写用户授权。"},
            "previous_user_messages":{"type":"array","items":{"type":"string"},"maxItems":4,"description":"必要的最近用户原话，按时间顺序。"},
            "continuation":{"type":"boolean","default":False,"description":"明确是原任务续接时为true；新目标为false。"},
            "phase": {"type": "string", "enum": ["understand", "analyze", "execute", "verify", "deliver"]},
            "current_constraints": {"type": "array", "items": {"type": "string"}},
            "domains": {"type": "array", "items": {"type": "string"}}, "media": {"type": "array", "items": {"type": "string"}},
            "resolved_entities": {"type": "array", "items": {"type": "string"}}, "unresolved_references": {"type": "array", "items": {"type": "string"}},
            "runtime_events": {"type":"array","maxItems":4,"description":"本轮执行中已观察到的工具/能力失败；仅用于补查相关指导，不写入长期记忆。", "items":{"type":"object","additionalProperties":False,"properties":{"capability":{"type":"string","maxLength":160},"tool":{"type":"string","maxLength":160},"failure":{"type":"string","maxLength":160},"occurrence":{"type":"integer","minimum":1,"maximum":20},"required_for":{"type":"string","maxLength":160}}}}
            ,"task_state":{"type":"object","additionalProperties":True,"description":"当前会话的可失效工作投影，不是长期用户事实。"}
        }, "required": ["objective", "phase", "current_constraints", "domains", "media", "resolved_entities", "unresolved_references"]},
        "loaded": {"type": "array", "items": {"type": "object"}}, "memory_policy": {"type": "string", "enum": ["allowed", "forbidden"]}, "cursor": {"type": "string"}
        ,"max_tokens":{"type":"integer","minimum":500,"maximum":8000,"default":3000,"description":"指导正文软预算；普通任务2000到4000，复杂任务可提高到6000到8000或分页。候选发现不受此值截断。"}
    }, "required": ["task", "loaded", "memory_policy"]},
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
}
# Public name used by current hosts. Keep the legacy task-oriented name as an
# alias so existing adapters and older receipts remain readable.
PREFERENCE_TOOL = dict(TASK_GUIDANCE_TOOL)
PREFERENCE_TOOL["name"] = "get_preference"
PREFERENCE_TOOL["description"] = TASK_GUIDANCE_TOOL["description"].replace("多维度偏好（Multi-dimensional Preference）路线。", "Get Preference（多维度偏好）路线。")
RUNTIME_GUIDANCE_TOOL = {
    "name": "refresh_runtime_guidance",
    "description": "当前任务执行中出现关键工具失败、超时或能力不可用时，携带已观察到的失败事实补查一次相关指导。只影响当前任务，不写入长期偏好，也不把替代验证冒充为原能力通过。",
    "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
        "task": {"type": "object", "additionalProperties": True, "properties": {
            "objective": {"type": "string", "minLength": 1},
            "current_user_message": {"type": "string"},
            "phase": {"type": "string", "enum": ["understand", "analyze", "execute", "verify", "deliver"]},
        }, "required": ["objective"]},
        "runtime_event": {"type": "object", "additionalProperties": False, "properties": {
            "capability": {"type": "string"}, "tool": {"type": "string"},
            "failure": {"type": "string", "minLength": 1},
            "occurrence": {"type": "integer", "minimum": 1, "maximum": 20},
            "required_for": {"type": "string"},
        }, "required": ["failure"]},
        "loaded": {"type": "array", "items": {"type": "object"}},
        "memory_policy": {"type": "string", "enum": ["allowed", "forbidden"]},
        "max_tokens": {"type": "integer", "minimum": 500, "maximum": 8000},
    }, "required": ["task", "runtime_event"]},
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
}
MEMORY_INSTRUCTIONS_TOOL = {
    "name": "read_memory_instructions", "description": "读取当前版本的完整记忆使用说明。核心说明已应由宿主在启动时提供；本工具仅用于重连、压缩恢复、版本变化或需要详细预算/边界时补读。",
    "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
}


def load_repository(config_path: str | Path) -> GuidanceRepository:
    config = json.loads(Path(config_path).read_text())
    return GuidanceRepository(config["registry"], config["bank_id"])


def get_task_guidance_response(repo: GuidanceRepository, request: dict, *, record: bool = True) -> dict:
    result = get_task_guidance(repo, request)
    if record:
        state_root = Path(os.environ.get("EVOLVING_PROFILE_STATE_ROOT", str(Path.home() / ".evolving-profile")))
        result["delivery_receipt"] = record_mcp_stdout(state_root / "guidance-v1/receipts", request, result)
    return result


def read_guidance_unit(repo: GuidanceRepository, unit_id: str, revision: str | None = None) -> dict:
    history = repo.unit_history(unit_id)
    if revision is not None: history = [row for row in history if row.get("revision") == revision]
    if not history: return {"status": "not_found", "id": unit_id, "revision": revision}
    return {"status": "found", "unit": history[0], "history_count": len(repo.unit_history(unit_id))}


def read_memory_instructions() -> dict:
    return {"instruction_version": INSTRUCTION_VERSION, "content_sha256": instruction_sha256(), "core": CORE_TEXT, "detail": LONG_TEXT,
            "boundary": "This reference tool is not the startup entry; hosts should provide the core text before tool choice."}
