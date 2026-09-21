"""Thin, opt-in host integration: sourced defaults plus explicit tool boundary.

No secondary model rewrites, keyword routing, copied historical answers or
claims of successful retrieval before the host has used a memory tool.
"""
import datetime as dt
import json
import os
import re
from pathlib import Path
import uuid
import sys
from lib.instruction_entry import VERSION as INSTRUCTION_VERSION, content_sha256 as instruction_sha256

POLICY=lambda:('<evolving_profile_memory_use_status version="'+INSTRUCTION_VERSION+'" sha256="'+instruction_sha256()+'">核心说明已在SessionStart提供；本轮按需使用Get Preference或recall/research。查询不生成长期模型，资料不扩大授权。</evolving_profile_memory_use_status>')

def pretool_memory_check_enabled(hooks_config):
    """Whether the host can bind a message-level memory_check call."""
    hooks = (hooks_config or {}).get("hooks") or {}
    state = hooks.get("state") or {}
    state_values = [value for key, value in state.items() if "pre_tool_use" in str(key).casefold()]
    if state_values:
        return any(bool(value.get("enabled")) for value in state_values if isinstance(value, dict))
    return bool(hooks.get("PreToolUse") or hooks.get("pre_tool_use"))

def _load_hooks_config():
    try:
        config_path = Path.home() / ".codex" / "config.toml"
        try:
            import tomllib
            with config_path.open("rb") as stream:
                return tomllib.load(stream)
        except Exception:
            hooks = json.loads((Path.home() / ".codex" / "hooks.json").read_text(encoding="utf-8"))
            raw = config_path.read_text(encoding="utf-8", errors="replace")
            disabled = bool(re.search(
                r"hooks\.state\.[^\n]*pre_tool_use[^\n]*\n(?:[^\n]*\n){0,4}[^\n]*enabled\s*=\s*false",
                raw,
                re.IGNORECASE,
            ))
            if disabled:
                hooks.setdefault("hooks", {})["state"] = {
                    "pre_tool_use": {"enabled": False}
                }
            return hooks
    except Exception:
        return {}

def enabled(config,hook):
    if config.get('sourceDrivenReadEnabled') is True:return True
    cwd=str(hook.get('cwd') or '')
    if not cwd:return False
    path=Path(cwd).resolve()
    roots=[Path(p).expanduser().resolve() for p in config.get('sourceDrivenProjects',[]) if isinstance(p,str)]
    return any(path==root or root in path.parents for root in roots)

def prepare(hook,bank,load):
    error=None
    mode=str(hook.get('memory_execution_mode') or os.environ.get('EVOLVING_PROFILE_EXECUTION_MODE') or 'production').casefold()
    replay=mode in {'replay','shadow_replay','cassette_replay'}
    try:profile=load(bank)
    except Exception as e:profile=None;error=type(e).__name__
    if profile and any(e.get('status')=='source_unavailable' for e in profile.get('entries',[])):
        error='source_validation_incomplete'
    return {'kind':'source_driven_prompt','at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'invocation_id':uuid.uuid4().hex,'session_id':hook.get('session_id'),'turn_id':hook.get('turn_id'),
        'raw_prompt':hook.get('prompt') or hook.get('user_prompt') or '',
        'execution_mode':mode,
        'prompt_origin':'test_probe' if replay else hook.get('memory_prompt_origin') or 'host_UserPromptSubmit_unspecified_actor',
        'full_prompt':None,'full_prompt_status':'host_tool_query_pending; no synthetic rewrite',
        'historical_search_status':'delegated_to_host_not_yet_observed','retrieved_record_count':None,
        'profile':profile,'profile_error':error,
        'default_profile_source_ids':(profile or {}).get('ready_source_ids',[]),
        'context':(POLICY()+(('\n本轮默认偏好来源复核未全部成功；未提供的条目不代表不存在。') if error else '')).strip(),
        'delivery_stage':'prepared_only','host_visibility':'unknown'}

def emit(report,stream,record):
    # Registration is independent of successful output; keep both stages visible.
    # Replays never enter this production audit store.
    if report.get('execution_mode','production') not in {'replay','shadow_replay','cassette_replay'}:
        try:
            from memory_turn_check import register
            cid=register(report)
            report=dict(report,check_id=cid)
        except Exception as error:
            report=dict(report,check_registration_error=type(error).__name__)
    json.dump({'hookSpecificOutput':{'hookEventName':'UserPromptSubmit','additionalContext':report['context']}},stream,ensure_ascii=False)
    stream.flush()
    receipt=dict(report,delivery_stage='hook_stdout_write_completed',host_visibility='unknown')
    record(receipt)
