def test_no_hook_does_not_claim_every_turn_or_replace_source_verification():
    from lib.host_integration.guidance import render_host_guidance
    result=render_host_guidance({'id':'doubao_work'},{'capabilities':{}},'en')
    assert result['trigger_mode']=='best_effort'
    assert result['mandatory_each_turn'] is False
    assert 'user_recall' in result['text'] and 'read_source' in result['text']
    assert '原文' not in result['text']
    assert result['capture_enabled'] is False


def test_chinese_guide_and_current_prompt_precedence():
    from lib.host_integration.guidance import render_host_guidance
    result=render_host_guidance({'id':'workbuddy'},{'capabilities':{}},'zh-CN')
    assert '当前' in result['text'] and 'user_preference' in result['text']
    assert result['current_prompt_wins'] is True


def test_new_host_hook_is_fail_open_and_never_runs_codex_retention(monkeypatch,capsys):
    from lib.host_integration.guidance import guard_non_codex_hook
    monkeypatch.setenv('EVOLVING_PROFILE_HOST_ID','doubao_work')
    assert guard_non_codex_hook({'hook_event_name':'Stop'}) is True
    assert capsys.readouterr().out==''
    assert guard_non_codex_hook({'hook_event_name':'UserPromptSubmit'}) is True
    assert 'additionalContext' in capsys.readouterr().out
