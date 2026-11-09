import pytest


def test_hidden_tool_direct_call_is_denied():
    from lib.host_integration.policy import allowed_tool_names,authorize_tool_call
    assert 'promote_agent_process_memory' not in allowed_tool_names({}, {})
    with pytest.raises(PermissionError):authorize_tool_call('promote_agent_process_memory',{}, {})
    authorize_tool_call('user_recall',{'query':'q'}, {})


def test_operator_allowlist_cannot_be_widened_by_arguments():
    from lib.host_integration.policy import authorize_tool_call
    with pytest.raises(PermissionError):authorize_tool_call('user_research',{'allow_all':True},{'allowed_tools':['user_recall']})


def test_unknown_tool_and_alias_denied():
    from lib.host_integration.policy import authorize_tool_call
    for tool in ('retain','get_task_guidance','new_future_tool'):
        with pytest.raises(PermissionError):authorize_tool_call(tool,{}, {})
