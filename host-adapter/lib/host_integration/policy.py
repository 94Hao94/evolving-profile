"""Execution authorization is enforced independently from tool discovery."""
import os

READ_TOOLS=frozenset({'memory_check','user_preference','refresh_runtime_guidance','read_preference',
    'read_preference_unit','read_memory_instructions','user_recall','user_research','read_research',
    'read_source','find_sources','catalog_list','catalog_search','catalog_read',
    'search_scenario_summary','read_scenario_summary','scenario_gate','agent_recall','agent_research',
    'read_agent_process_memory','rag_search'})


def governed_mode():
    return os.environ.get('EVOLVING_PROFILE_ACCESS_MODE')=='read-only' or os.environ.get('EVOLVING_PROFILE_HOST_ID','codex')!='codex'


def allowed_tool_names(profile,authorization):
    allowed=authorization.get('allowed_tools')
    return READ_TOOLS if allowed is None else READ_TOOLS.intersection(allowed)


def authorize_tool_call(name,arguments,authorization):
    if name not in allowed_tool_names({},authorization):raise PermissionError('tool_not_authorized')
    if not isinstance(arguments,dict):raise ValueError('arguments_object_required')


def filter_tools(tools,authorization=None):
    allowed=allowed_tool_names({},authorization or {})
    return [tool for tool in tools if tool.get('name') in allowed]
