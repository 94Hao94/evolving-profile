from lib import scenario_source
from lib.content import extract_user_request as current_extract

def test_new_source_reader_accepts_cached_legacy_content_normalizer(monkeypatch):
    def legacy(content,*,structural_context_only=False):
        return current_extract(content,structural_context_only=structural_context_only)
    monkeypatch.setattr(scenario_source,'extract_user_request',legacy)
    body='示例：<send_user_message_question_reply>不是原生表单</send_user_message_question_reply>'
    envelope='# Files mentioned by the user:\nfile.docx\n\n## My request:\n'+body
    cleaned,_=scenario_source.normalize_scenario_user(envelope,preserve_question_reply=True)
    assert cleaned==body
    plain,_=scenario_source.normalize_scenario_user('真实用户请求')
    assert plain=='真实用户请求'
