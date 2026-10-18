"""Fallback navigation must retain file identity and the authored request."""
import pytest
from lib.scenario_model import deterministic_source_state_draft
from test_scenario_state_v3 import source


def draft(text,answer=None):
    rows=[('user',text)]
    if answer is not None:rows.append(('assistant',answer))
    return deterministic_source_state_draft(source(rows))


def test_long_directory_prefix_cannot_replace_task_or_cut_file_identity():
    name='课程_'+('A'*85)+'_最终版.docx';path='/workspace/'+('nested/'*30)+name
    goal='请改写讲稿，保留12页和原有受众范围。'
    result=draft(path+' '+goal)
    assert result['state']['subject']['text']==name
    assert result['state']['goal']['text']==goal
    assert result['state']['unresolved'][0]['text']==goal
    assert path in result['summaries']['full']
    assert result['review_status']=='pending_independent_review'


@pytest.mark.parametrize('path,name',[
    ('"C:\\project folder\\Outline final.docx"','Outline final.docx'),
    ('"/workspace/project folder/课程教案.md"','课程教案.md'),
    ('./materials/notes.md','notes.md'),
    ('../materials/notes.md','notes.md'),
])
def test_explicit_cross_platform_paths_keep_the_real_request(path,name):
    goal='Improve the outline without changing its scope.'
    result=draft(path+' '+goal)
    assert result['state']['subject']['text']==name
    assert result['state']['goal']['text']==goal


def test_url_and_inline_path_prose_are_not_reclassified_as_file_prefixes():
    for text in ['https://example.org/topic Explain this reference.','请解释 /tmp/result.md 这个路径的含义。']:
        assert draft(text)['state']['goal']['text']==text


def test_fallback_does_not_add_a_second_assistant_report_label():
    answer='The outline is ready; the external delivery is not verified.'
    result=draft('Prepare the outline.',answer)
    assert result['state']['assistant_reports'][0]['text']==answer
    assert result['summaries']['full'].count('助手报告（未独立核验）')==1


def test_path_only_does_not_invent_an_edit_or_generation_goal():
    result=draft('/workspace/outline.docx')
    assert result['state']['subject']['text']=='outline.docx'
    assert '待确认' in result['state']['goal']['text']
    assert '修改' not in result['state']['goal']['text']
    assert result['source_linked_fallback']['semantic_completeness_proven'] is False


def test_multiple_leading_files_do_not_swallow_the_comparison_request():
    result=draft('/workspace/a.docx /workspace/b.docx Compare the two versions.')
    assert 'a.docx' in result['state']['subject']['text']
    assert 'b.docx' in result['state']['subject']['text']
    assert result['state']['goal']['text']=='Compare the two versions.'


def test_oversized_filename_is_explicitly_abbreviated_and_remains_in_full_source_fields():
    name='a'*220+'.docx';result=draft('/workspace/'+name+' 请检查来源。')
    assert '名称缩略' in result['state']['subject']['text']
    assert '.docx' in result['state']['subject']['text']
    assert len(result['state']['subject']['text'])<=180
    assert name in result['summaries']['full']


def test_long_main_request_is_not_replaced_by_a_later_short_constraint():
    main='请逐节比较原稿与修订稿中的因果说明并列出差异'+('并保留各项说明的原始定位和版本信息'*14)
    result=draft('/workspace/report.docx '+main+'；不要发布。')
    assert result['state']['goal']['text'].startswith('请逐节比较原稿')
    assert result['state']['goal']['text'].endswith('…')
    assert result['state']['unresolved'][0]['text'].startswith('请逐节比较原稿')
    assert '不要发布。' in result['summaries']['full']


def test_unquoted_spaced_path_boundary_is_explicitly_uncertain_not_guessed():
    text='/workspace/project folder/outline.docx Improve the outline.'
    result=draft(text)
    assert '待确认' in result['state']['subject']['text']
    assert '待确认' in result['state']['goal']['text']
    assert text in result['summaries']['full']
