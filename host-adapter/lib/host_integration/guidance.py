"""Short advisory entry; a Skill or MCP description is not a lifecycle hook."""
import json
import os
import sys
from .registry import get_profile,load_registry


def render_host_guidance(profile,readiness,locale):
    observed=readiness.get('capabilities',{}).get('prompt_hook',{}).get('state')=='host_verified'
    if locale.startswith('zh'):
        text=('当前用户要求优先。涉及个人历史或协作习惯时使用 user_preference、user_recall/user_research；'
              '执行经验使用 agent_recall/agent_research。范围有歧义时先 search_scenario_summary，'
              '按需 read_scenario_summary；重要事实通过 read_source 回读原文。候选不是事实。'
              '使用本轮真实绑定，不借用其他宿主或旧轮次的 check_id。服务不可用如实报告；'
              '不要宣称每轮自动执行或未经验证的送达、回答采用。不要自动写入长期记忆。')
    else:
        text=('Current user instructions take precedence. Use user_preference and user_recall/user_research '
              'for applicable preferences and user history; agent_recall/agent_research for execution experience. '
              'Resolve ambiguous scope with search_scenario_summary and, when useful, read_scenario_summary. '
              'Verify important facts through read_source. Candidates are not verified facts. Use only the '
              'current genuine binding; never borrow another host or turn check_id. Report unavailable '
              'services and unknown delivery honestly. No automatic long-term writes or per-turn guarantee.')
    return {'schema':'ep.host-guidance.v1','host_id':profile['id'],'text':text,
            'trigger_mode':'native_event_verified' if observed else 'best_effort',
            'mandatory_each_turn':False,'capture_enabled':False,'current_prompt_wins':True}


def guard_non_codex_hook(raw):
    host=os.environ.get('EVOLVING_PROFILE_HOST_ID','codex')
    if host=='codex':return False
    try:
        profile=get_profile(load_registry(),host)
        if raw.get('hook_event_name') in ('SessionStart','UserPromptSubmit'):
            guide=render_host_guidance(profile,{},os.environ.get('EVOLVING_PROFILE_LOCALE','en'))
            print(json.dumps({'hookSpecificOutput':{'hookEventName':raw['hook_event_name'],
                'additionalContext':guide['text']}},ensure_ascii=False))
        print('EP host capture remains disabled: native source/host validation required',file=sys.stderr)
    except (ValueError,OSError,TypeError):
        print('EP host entry unavailable; continue without automatic capture',file=sys.stderr)
    return True


def route_external_hook():
    if os.environ.get('EVOLVING_PROFILE_HOST_ID','codex')=='codex':return False
    try:
        body=sys.stdin.read(1024*1024+1)
        if len(body)>1024*1024:raise ValueError('hook_budget_exceeded')
        raw=json.loads(body)
        if not isinstance(raw,dict):raise ValueError('invalid_hook')
        guard_non_codex_hook(raw)
    except (ValueError,OSError,TypeError):
        print('EP host event unavailable; continuing',file=sys.stderr)
    return True
