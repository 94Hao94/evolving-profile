#!/usr/bin/env python3
"""Forced UserPromptSubmit task-guidance entry check.

This is the host adapter boundary for the guidance MCP implementation.  It
invokes the same read-only GuidanceRepository selector used by
``get_task_guidance`` and records that the check happened.  It does not run
historical recall, research, source reads, or long-term publication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import sys
import uuid
from lib.instruction_entry import VERSION, instruction_block, instruction_receipt
from task_state import TaskStateStore
from lib.memory_policy import classify_memory_policy
from entry_navigation import build_navigation_map

GUIDANCE_SRC = Path("$HOME/.evolving-profile/runtime/guidance")
GUIDANCE_CONFIG = Path("$HOME/.evolving-profile/guidance-v1/guidance-v1.json")
RECEIPT_ROOT = Path.home() / ".evolving-profile/audit/guidance-entry-receipts"
MAX_TOKENS = 5000
MAX_CONTEXT_CHARS = 9000
AGENT_ENTRY_MAX_CONTEXT_CHARS = 9000
PROMPT_INGRESS = Path.home() / ".evolving-profile" / "audit" / "prompt-ingress.jsonl"
TASK_STATE_ROOT = Path.home() / ".evolving-profile" / "task-state"


def _continuation_only(text: str) -> bool:
    value=re.sub(r'[\s，。！？!?、,]+','',str(text or ''))
    simple=bool(re.fullmatch(r'(?:那|你|就|赶紧|啊|吧|好|好的|可以|继续|接着|执行|开工|开始|处理|不要停|别停|都完事儿了吗)+',value))
    referenced=bool(re.fullmatch(r'(?:那)?(?:你)?(?:就)?按(?:你|上面|刚才)(?:的)?(?:建议|方案|思路)(?:的)?(?:执行|处理|继续|做)(?:吧|啊)?',value))
    repair=bool(re.fullmatch(r'(?:那|这个|这件事|刚才|上面|上述)?(?:你)?(?:建议)?(?:怎么|如何)?(?:修|修改|改|优化|处理|做|解决|推进)(?:好|完|下|一下)?(?:呢|啊|吧)?',value))
    return simple or referenced or repair


def _active_context(hook_input: dict, current_prompt: str) -> str:
    supplied = str(hook_input.get("memory_full_prompt") or "").strip()
    if supplied:
        return supplied
    session_id = str(hook_input.get("session_id") or "").strip()
    if not session_id or not PROMPT_INGRESS.is_file():
        return ""
    try:
        # Read a bounded tail: it contains the most recent ingress rows while
        # avoiding a full history scan at UserPromptSubmit.
        with PROMPT_INGRESS.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 512_000))
            rows = stream.read().decode("utf-8", errors="ignore").splitlines()
        for raw in reversed(rows):
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if str(row.get("session_id") or "") != session_id:
                continue
            prior = str(row.get("prompt_preview") or row.get("prompt") or "").strip()
            if prior and prior != current_prompt and not _continuation_only(prior):
                return f"前一项活动任务：{prior[:1200]}"
    except OSError:
        pass
    return ""


def _phase(prompt: str) -> str:
    value = str(prompt or "")
    if any(term in value for term in ("验收", "测试", "验证", "回归", "审计", "核对")):
        return "verify"
    if any(term in value for term in ("交付", "发布", "发送", "写成", "整理成")):
        return "deliver"
    if any(term in value for term in ("分析", "判断", "比较", "为什么", "原因", "权衡")):
        return "analyze"
    if any(term in value for term in ("解释", "讲讲", "怎么理解", "机制", "原理")):
        return "understand"
    return "execute" if any(term in value for term in ("继续", "修复", "修改", "推进", "开始", "开工")) else "understand"


def simple_self_contained(prompt: str) -> bool:
    value = "".join(str(prompt or "").split()).casefold()
    return value in {"你好", "您好", "嗨", "hi", "hello", "hey", "谢谢", "谢谢你", "好的", "收到"}


def preference_memory_policy(prompt: str, requested: str = "allowed") -> str:
    classified = classify_memory_policy(prompt)["guidance_memory_policy"]
    return "forbidden" if requested == "forbidden" or classified == "forbidden" else "allowed"


def build_request(hook_input: dict, prompt: str, context_ref: str, *, memory_policy: str = "allowed") -> dict:
    value = str(prompt or "").strip()
    normalized = re.sub(r"\s+", "", value).casefold()
    active_context = _active_context(hook_input, value) if classify_memory_policy(value)['history_allowed'] else ''
    if re.search(r'换个话题|另一个问题|新任务',value) or simple_self_contained(value):active_context=''
    explicit_continuation = _continuation_only(value) or value.startswith(("继续", "接着")) or bool(
        active_context and re.match(r"^(?:开工|开始执行|开始修|按(?:你|上面|刚才).{0,8}(?:建议|方案|思路))", value)
    )
    # A compact “再检查下” is a continuation only when the host supplied a
    # bounded active-task reconstruction. Without that evidence it remains a
    # self-contained request rather than inheriting arbitrary prior work.
    recheck_continuation = bool(
        active_context
        and len(normalized) <= 96
        and any(marker in normalized for marker in ("再检查", "再检察", "检查下", "检察下"))
    )
    continuation = explicit_continuation or recheck_continuation
    if not continuation:
        active_context = ""
    phase = _phase(value)
    return {
        "context_ref": context_ref,
        "task": {
            "objective": value or "本轮用户消息入口检查",
            "current_user_message": value,
            "context_summary": active_context[:6000],
            "previous_user_messages": [],
            "continuation": continuation,
            "phase": phase,
            "current_constraints": ["当前用户 Prompt 优先", "多维度偏好仅作 advisory reference"],
            "domains": [],
            "media": [],
            "resolved_entities": [],
            "unresolved_references": [],
        },
        "loaded": [],
        "memory_policy": preference_memory_policy(value, memory_policy),
        "max_tokens": MAX_TOKENS,
        "entry_adapter": True,
        # The Hook is the production entry path.  Keep command-line evaluation
        # deterministic unless it explicitly opts in, while every submitted
        # user prompt gets semantic candidate discovery with safe fallback.
        "semantic_recall": "local",
    }


def _call_task_guidance(request: dict) -> dict:
    if str(GUIDANCE_SRC) not in sys.path:
        sys.path.insert(0, str(GUIDANCE_SRC))
    script_root = str(Path(__file__).resolve().parent)
    if script_root not in sys.path:
        sys.path.insert(0, script_root)
    # Call the same implementation behind the registered
    # mcp__evolving_profile_controller__get_task_guidance tool. The stdio server is a
    # line-oriented process and must not be imported from a Hook (it would
    # consume the Hook stdin); the entry adapter uses its underlying runtime
    # function directly and records the boundary separately.
    from mcp_runtime import load_repository, get_task_guidance_response
    return get_task_guidance_response(load_repository(GUIDANCE_CONFIG), request, record=False)


def _entry_relevant(prompt: str, item: dict) -> bool:
    """Drop narrow topic guidance when the entry query has no matching anchor."""
    query = "".join(str(prompt or "").split()).casefold()
    text = "".join(" ".join(str(item.get(key) or "") for key in ("text", "applies_when", "exceptions")).split()).casefold()
    # The current Evolving Profile product supersedes a narrow earlier rule
    # that required preserving the original Hindsight product wholesale. Keep
    # it in the registry for historical audit, but do not inject it as current
    # guidance merely because the prompt mentions the memory system.
    obsolete_markers = ("原版hindsight", "完整保留", "严禁删减", "轻量原型", "替代memory.md", "绕过hook")
    if "evolvingprofile" in query and "hindsight" in text and sum(marker in text for marker in obsolete_markers) >= 2:
        return False
    # Avoid returning a PPT/Word/Excel-specific preference for a generic UI
    # or test task. The task can still page the original result if needed.
    narrow = re.findall(r"[a-z][a-z0-9+.#-]{2,}", text)
    for token in narrow:
        if token.upper() in {"PPT", "PPTX", "WORD", "EXCEL", "PDF", "DOCX"} and token not in query:
            return False
    return True


def render_entry(result: dict, prompt: str = "") -> tuple[str, dict]:
    stable = list(result.get("stable_profile") or [])
    raw_included = list(result.get("included") or [])
    included = raw_included
    models = list(result.get("model_sections") or [])
    deferred = list(result.get("deferred") or [])
    rendered_stable, rendered_items, rendered_models, bodies = [], [], [], []
    used = 0
    included_ids={str(item.get('id') or '') for item in included}
    stable=[item for item in stable if str(item.get('id') or '') not in included_ids]
    for kind, items, rendered in (("稳定协作骨架", stable, rendered_stable), ("候选偏好", included, rendered_items), ("融合心智模型", models, rendered_models)):
        for item in items:
            identity = str(item.get('id') or item.get('section_id') or '')
            text = str(item.get('text') or item.get('content') or '')
            body = f"- {kind} {identity}：{text}"
            for field, label in (('scope', '作用范围'), ('applies_when', '适用条件'), ('exceptions', '例外'), ('effect_on_action', '行动影响')):
                if item.get(field):
                    body += '\n  ' + label + '：' + (item[field] if isinstance(item[field], str) else json.dumps(item[field], ensure_ascii=False))
            if not text or used + len(body) > MAX_CONTEXT_CHARS:
                deferred.append({'id': identity, 'revision': item.get('revision'), 'reason': 'entry_body_budget', 'kind': kind})
                continue
            bodies.append(body)
            rendered.append(item)
            used += len(body)
    coverage = str(result.get("coverage") or "unknown")
    if len(deferred) > len(result.get('deferred') or []):
        coverage = 'partial_entry_body_with_deferred'
    deferred_previews = []
    for item in deferred:
        text = str(item.get('text') or '')
        if not text:
            continue
        preview = f"- 可展开偏好摘要 {item.get('id')}: {text}"
        if item.get('applies_when'):
            preview += "\n  适用条件摘要：" + (item['applies_when'] if isinstance(item['applies_when'], str) else json.dumps(item['applies_when'], ensure_ascii=False))
        if len(preview) <= MAX_CONTEXT_CHARS:
            deferred_previews.append(preview)
    lines = [
        f"<evolving_profile_guidance_entry version=\"{VERSION}\" mode=\"forced_task_guidance_check\">",
        "入口适配层已执行一次 Get Preference 检查；结果只是多维度偏好参考。当前用户 Prompt 优先；当前权威来源、工具结果和权限优先。",
        f"coverage={coverage}；{len(rendered_stable)} 条稳定协作骨架；{len(rendered_items)} 条候选偏好已注入；{len(rendered_models)} 个模型章节正文；{len(deferred)} 条可展开完整条件。",
    ]
    if deferred_previews:
        lines.append("候选摘要与适用条件（完整正文仍可按 ID 展开）：")
        lines.extend(deferred_previews)
    if bodies:
        lines.append("协作骨架与候选（候选仍需当前Agent逐条核对条件和例外）：")
        lines.extend(bodies)
    else:
        lines.append("本轮未读取多维度偏好正文；需要时再按任务缺口读取。")
    if deferred:
        lines.append("候选摘要已进入上下文；需要完整正文、例外或来源核对时可按 ID 展开。")
        lines.append('可展开 ID：' + '、'.join(str(item.get('id') or item.get('section_id') or '') for item in deferred[:8]))
        if len(deferred) > 8:
            lines.append('其余待补读项通过 Get Preference 分页获取。')
    lines.append("查询不生成长期模型，也不扩大用户授权。</evolving_profile_guidance_entry>")
    value = instruction_block('user-prompt-submit') + '\n' + "\n".join(lines)
    return value, {'stable_profile':rendered_stable,'included': rendered_items, 'preference_candidates':rendered_items, 'model_sections': rendered_models, 'deferred': deferred, 'coverage': coverage}


def format_context(result: dict, prompt: str = "") -> str:
    return render_entry(result, prompt)[0]


def _task_state_context(task_state: dict, session_id: str, budget: int) -> str:
    """Bound a duplicate task preview without cutting the manual/map or JSON."""
    start, end = '\n<evolving_profile_task_state>\n', '\n</evolving_profile_task_state>'
    fields = ('current_objective','current_message','continuation','continuation_context','source','authority','version',
              'update_reason','expires_at','constraints','completed','unresolved','objects','source_versions')
    block = {key:task_state[key] for key in fields if task_state.get(key) is not None}

    def render(value):
        return start + json.dumps(value, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c') + end

    full = render(block)
    if len(full) <= budget:
        return full
    # Full state remains in the local task store and the entry receipt. The
    # current user message is already visible to the Agent, so do not repeat it.
    block.pop('current_message', None)
    block.update(projection_truncated=True, full_state_file=str(TASK_STATE_ROOT / (hashlib.sha256(session_id.encode()).hexdigest()+'.json')))
    for limit in (160, 80, 40):
        preview = {key:(value if key in ('version','continuation','projection_truncated','full_state_file')
                        else (str(value) if isinstance(value,str) else json.dumps(value,ensure_ascii=False))[:limit])
                   for key,value in block.items()}
        rendered = render(preview)
        if len(rendered) <= budget:
            return rendered
    return render({key:block[key] for key in ('version','projection_truncated','full_state_file')})


def prepare_agent_owned_entry(hook_input: dict, prompt: str, *, memory_policy: str = "allowed") -> dict:
    """Supply L0 navigation plus a bounded Get Preference candidate packet."""
    invocation=str(hook_input.get('hook_invocation_id') or uuid.uuid4().hex)
    request=build_request(hook_input,prompt,'entry:'+invocation,memory_policy=memory_policy)
    policy=classify_memory_policy(prompt)
    policy['guidance_memory_policy']=request['memory_policy']
    navigation_context,navigation=build_navigation_map(GUIDANCE_CONFIG,policy)
    task_state=None;session_id=str(hook_input.get('session_id') or '').strip()
    if session_id:
        try:
            task_state=TaskStateStore(TASK_STATE_ROOT).record(
                session_id,prompt,hook_input.get('turn_id'),invocation,
                continuation=bool(request['task'].get('continuation')) and policy['history_allowed'],
            )
        except OSError:task_state=None
    context=instruction_block('user-prompt-submit')+'\n'+navigation_context+'\n'+(
        '<evolving_profile_guidance_entry version="'+VERSION+'" mode="navigation_plus_get_preference_candidate_packet">'
        '入口已提供轻量偏好与Bank地图，并附带有界的Get Preference候选包；候选仍由当前Agent结合完整Prompt判断是否展开或采用。'
        'Get Preference不是完整偏好注入；需要时继续按ID补读。'
        '据证据缺口调用catalog/recall/research/read_source；不得仅因当前上下文看似足够而跳过地图检查。'
        '</evolving_profile_guidance_entry>'
    )
    guidance_result=None;guidance_rendered={'stable_profile':[],'included':[],'preference_candidates':[],'model_sections':[],'deferred':[],'coverage':'not_requested'}
    if request.get('memory_policy') != 'forbidden' and not simple_self_contained(prompt):
        try:
            candidate_request=dict(request,max_tokens=5000)
            guidance_result=_call_task_guidance(candidate_request)
            guidance_context,guidance_rendered=render_entry(guidance_result,prompt)
            remaining=max(0,AGENT_ENTRY_MAX_CONTEXT_CHARS-len(context)-320)
            if remaining:
                context += '\n' + guidance_context[:remaining]
        except Exception:
            guidance_result={'coverage':'unavailable','included':[],'deferred':[]}
            guidance_rendered['coverage']='unavailable'
    if task_state:
        context+=_task_state_context(task_state,session_id,AGENT_ENTRY_MAX_CONTEXT_CHARS-len(context))
    receipt={
        'schema':'hindsight.guidance-entry-check.v1','kind':'guidance_entry_check','tool_name':'get_preference','legacy_tool_name':'get_task_guidance',
        'invocation_mode':'navigation_plus_get_preference_candidate_packet','delivery_stage':'navigation_and_guidance_candidates_prepared',
        'host_visibility':'hook_context_pending','at':datetime.now(timezone.utc).isoformat(),
        'session_id':hook_input.get('session_id'),'turn_id':hook_input.get('turn_id'),'hook_invocation_id':invocation,
        'request':request,'task_state':task_state,'instruction':instruction_receipt(),'navigation_map':navigation,
        'rendered_guidance':guidance_rendered,
        'stable_profile_count':len(guidance_rendered.get('stable_profile') or []),'preference_candidate_count':len(guidance_rendered.get('preference_candidates') or []),'selection_revision':(guidance_result or {}).get('selection_revision'),'coverage':guidance_rendered.get('coverage') or 'not_requested',
        'included_count':len((guidance_result or {}).get('included') or []),'entry_context_included_count':len(guidance_rendered.get('included') or []),'model_section_count':len(guidance_rendered.get('model_sections') or []),'deferred_count':len(guidance_rendered.get('deferred') or []),
        'result':guidance_result,'context_chars':len(context),'context_sha256':hashlib.sha256(context.encode()).hexdigest(),'error':None,
    }
    try:
        RECEIPT_ROOT.mkdir(parents=True,exist_ok=True);target=RECEIPT_ROOT/(hashlib.sha256(invocation.encode()).hexdigest()+'.json');temporary=target.with_suffix('.tmp')
        temporary.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(target)
    except OSError:pass
    return {'result':None,'context':context,'receipt':receipt}


def run_entry_check(hook_input: dict, prompt: str, *, memory_policy: str = "allowed") -> dict:
    invocation = str(hook_input.get("hook_invocation_id") or uuid.uuid4().hex)
    request = build_request(hook_input, prompt, "entry:" + invocation, memory_policy=memory_policy)
    task_state = None
    session_id = str(hook_input.get("session_id") or "").strip()
    if session_id:
        try:
            task_state = TaskStateStore(TASK_STATE_ROOT).record(
                session_id, prompt, hook_input.get("turn_id"), invocation,
                continuation=bool(request["task"].get("continuation")),
            )
            request["task"]["task_state"] = {
                key: task_state.get(key) for key in (
                    "current_objective", "current_message", "continuation",
                    "continuation_context", "source", "authority", "version",
                    "update_reason", "expires_at", "constraints", "completed",
                    "unresolved", "objects", "source_versions",
                )
            }
        except OSError:
            task_state = None
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = _call_task_guidance(request)
        error = None
    except Exception as exc:  # Entry check must never block the user turn.
        result = {"coverage": "unavailable", "included": [], "model_sections": [], "deferred": [], "errors": [type(exc).__name__]}
        error = type(exc).__name__
    context, rendered = render_entry(result, prompt)
    if task_state:
        task_block = {
            key: task_state.get(key) for key in (
                "current_objective", "current_message", "continuation",
                "continuation_context", "source", "authority", "version",
                "update_reason", "expires_at", "constraints", "completed",
                "unresolved", "objects", "source_versions",
            )
        }
        context += "\n<evolving_profile_task_state>\n" + json.dumps(task_block, ensure_ascii=False) + "\n</evolving_profile_task_state>"
    receipt = {
        "schema": "hindsight.guidance-entry-check.v1",
        "kind": "guidance_entry_check",
        "tool_name": "get_preference",
        "legacy_tool_name": "get_task_guidance",
        "invocation_mode": "codex_UserPromptSubmit_entry_adapter",
        "delivery_stage": "entry_selected_then_hook_context_prepared",
        "host_visibility": "hook_context_pending",
        "at": started,
        "session_id": hook_input.get("session_id"),
        "turn_id": hook_input.get("turn_id"),
        "hook_invocation_id": invocation,
        "request": request,
        "task_state": task_state,
        "instruction": instruction_receipt(),
        "rendered_guidance": rendered,
        "stable_profile_count": len(rendered.get('stable_profile') or []),
        "preference_candidate_count": len(rendered.get('preference_candidates') or []),
        "selection_revision": result.get("selection_revision"),
        "coverage": rendered['coverage'],
        "included_count": len(result.get("included") or []),
        "entry_context_included_count": len(rendered['included']),
        "model_section_count": len(rendered['model_sections']),
        "deferred_count": len(rendered['deferred']),
        "result": result,
        "context_sha256": hashlib.sha256(context.encode("utf-8")).hexdigest(),
        "error": error,
    }
    try:
        RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)
        target = RECEIPT_ROOT / (hashlib.sha256(invocation.encode()).hexdigest() + ".json")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    except OSError:
        pass
    return {"result": result, "context": context, "receipt": receipt}
