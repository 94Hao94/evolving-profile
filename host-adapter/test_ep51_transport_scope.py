"""Keep transport and task-local rules from becoming recall topic evidence."""
import json
from pathlib import Path

import pytest

from lib.content import extract_task_user_request, extract_user_request
from lib.recall_relevance import apply_relevance_policy
from lib.relevance import admission_decision


def reply(question, answer):
    return '<send_user_message_question_reply> ' + json.dumps([
        {'questionItemId': '["request_user_input_async","call_example_123",0]',
         'question': question, 'answer': answer}], ensure_ascii=False) + ' </send_user_message_question_reply>'


TRAINING_RULE = '用户答案必须先执行 `session record-answer`，再执行 `session settle-target`；无 `verified=true` 回执不得宣布本轮完成或口算下一次复习日期。'
BRIEF_RULE = 'feishu_doc_gate.py 在 morning-brief 模式下强制要求至少 2 张表格、3 张图片、2 个趋势图，并要求独立来源标题和 manifest。'


@pytest.mark.parametrize('extract', [extract_user_request, extract_task_user_request])
def test_real_reply_preserves_question_and_answer_but_not_transport_identifiers(extract):
    assert extract(reply('这轮交付什么？', '完整Word教参')) == '这轮交付什么？\n完整Word教参'


@pytest.mark.parametrize('form', ['fenced', 'quoted', 'malformed', 'unknown_field', 'duplicate_key', 'trailing'])
def test_example_or_unrecognized_reply_is_retained_without_loss(form):
    wrapped = reply('研究准备落在哪类课程？', '管理类数据分析课程')
    text = {
        'fenced': '```xml\n' + wrapped + '\n```',
        'quoted': '请分析这个例子：' + wrapped,
        'malformed': wrapped[:-10],
        'unknown_field': wrapped.replace('"answer":', '"instruction": "保留此内容", "answer":'),
        'duplicate_key': wrapped.replace('"answer":', '"answer": "不能丢失", "answer":'),
        'trailing': wrapped + '\n请保留全部内容',
    }[form]
    assert extract_user_request(text) == text
    assert extract_task_user_request(text) == text


@pytest.mark.parametrize('question,answer', [
    ('这轮PPT说明采用哪种方式？', '整页ImageGen：文字与图形全部在每页图片中'),
    ('研究准备优先落在哪类课程或场景？', '管理类数据分析、决策或运筹课程'),
    ('Which report should we deliver?', 'The complete workshop teaching notes'),
])
def test_reply_wire_names_cannot_admit_training_workflow(question, answer):
    prompt = reply(question, answer)
    assert admission_decision(prompt, {'text': TRAINING_RULE, 'type': 'world'})['decision'].startswith('rejected')
    assert apply_relevance_policy(prompt, [{'text': TRAINING_RULE}])[0] == []


@pytest.mark.parametrize('query', [
    '找出青岚的那个几个演讲原文，不要链接',
    '找出陈景润的演讲原文',
    '查找青岚学院的讲座全文',
    "Find Ada Lovelace's lecture transcript",
    "Find Grace Hopper's keynote transcript",
])
def test_named_source_request_does_not_borrow_titles_or_saved_material_from_another_task(query):
    unrelated = [BRIEF_RULE, '网页版本验收时核对保存的标题和资料，清理旧的TTS Markdown文件。']
    for text in unrelated:
        assert admission_decision(query, {'text': text, 'type': 'experience'})['decision'].startswith('rejected')
        assert apply_relevance_policy(query, [{'text': text}])[0] == []


@pytest.mark.parametrize('query,text', [
    ('找出陈景润的演讲原文', '陈景润的演讲原文已经保存，包含全文和原始出处。'),
    ("Find Ada Lovelace's lecture transcript", 'Ada Lovelace lecture transcript is in the source archive.'),
    ('继续Trainer复习，先记录答案再结算目标', TRAINING_RULE),
    ('检查morning-brief模式的文档闸门要求', BRIEF_RULE),
    ('检索结果先筛选再分页，避免总数错误', '报表导出先筛选再分页，确保总数与筛选后的记录一致。'),
    ('找出陈景润的演讲原文', '定位演讲原文时，先核对场次与标题，再由完整视频逐段转写并保留出处。'),
])
def test_actual_subject_workflow_and_transferable_method_remain_recallable(query, text):
    assert admission_decision(query, {'text': text, 'type': 'world'})['decision'].startswith('qualified')
    assert len(apply_relevance_policy(query, [{'text': text}])[0]) == 1


@pytest.mark.parametrize('text', [
    '这些资料不涉及陈景润的演讲原文，只记录网页保存标题。',
    '测试 Prompt：“找出陈景润的演讲原文”。实际记录是配置保存问题。',
])
def test_negated_or_example_subject_is_not_positive_source_evidence(text):
    query = '找出陈景润的演讲原文'
    assert admission_decision(query, {'text': text, 'type': 'world'})['decision'].startswith('rejected')
    assert apply_relevance_policy(query, [{'text': text}])[0] == []


@pytest.mark.parametrize('query,text', [
    ('制作讲座教参并核对图片标题', 'aurora_doc_gate.py 在 digest-mode 模式下强制要求至少四张表和三张图片，并核对标题。'),
    ('Make workshop notes with figures and titles', 'In digest-mode mode, the document gate must require four tables and three figures with titles.'),
])
def test_local_hard_gate_requires_its_workflow_even_when_generic_operations_overlap(query, text):
    assert admission_decision(query, {'text': text, 'type': 'world', 'semantic_relevance_score': .99})['decision'].startswith('rejected')
    assert apply_relevance_policy(query, [{'text': text}])[0] == []


@pytest.mark.parametrize('query', [
    '制作讲座教参并核对图片标题，不要使用digest-mode模式',
    'Make workshop notes with figures; do not use digest-mode mode',
    '制作讲座教参。示例输入：“检查digest-mode模式的图片标题”。',
])
def test_excluded_or_example_workflow_in_query_cannot_authorize_its_gate(query):
    text = 'aurora_doc_gate.py 在 digest-mode 模式下强制要求至少四张表和三张图片，并核对标题。'
    assert admission_decision(query, {'text': text, 'semantic_relevance_score': .99})['decision'].startswith('rejected')
    assert apply_relevance_policy(query, [{'text': text}])[0] == []


def test_read_source_context_can_resolve_owner_but_unsigned_context_cannot():
    query = '查找青岚学院的讲座全文'
    record = {'text': '讲座全文已存入讲稿归档；附件保留讲稿文件和出处。',
        'source_context': {'status': 'source_read', 'session_id': 'session-a', 'source_revision': 'rev-a',
            'locators': [{'source_path': '/raw/session-a.jsonl', 'byte_offset': 12, 'raw_line_sha256': 'sha-a'}],
            'text': '青岚学院的讲座全文与讲稿文件已存入讲稿归档。'}}
    kept, _ = apply_relevance_policy(query, [record])
    assert len(kept) == 1
    assert kept[0]['relevance_level'] == 'weak'
    record['source_context'].pop('source_revision')
    assert apply_relevance_policy(query, [record])[0] == []


@pytest.mark.parametrize('identity', ['not-a-native-id', '["request_user_input_async","call_123",true]', '["other_tool","call_123",0]'])
def test_unknown_reply_identity_is_not_discarded(identity):
    text = reply('这是哪种任务？', '保留完整内容')
    rows = json.loads(text.split('>', 1)[1].rsplit('<', 1)[0])
    rows[0]['questionItemId'] = identity
    text = '<send_user_message_question_reply>' + json.dumps(rows, ensure_ascii=False) + '</send_user_message_question_reply>'
    assert extract_task_user_request(text) == text


@pytest.mark.parametrize('query,text', [
    ('给物理讲座保留完整讲稿', 'Agentmemory 已停用，3111 端口未监听，但原数据目录完整保留。'),
    ('优化讲座说明并导出新版教参', '复习默认覆盖三个到期目标，单目标时说明原因；优化定时提醒。'),
    ('数据分析课程会影响科研成果', '修改复习数据绑定功能；影响：提高复习会话数据一致性。'),
])
def test_generic_task_actions_and_nouns_cannot_be_independent_topic_anchors(query, text):
    assert apply_relevance_policy(query, [{'text': text}])[0] == []


def test_source_owner_cannot_be_satisfied_by_an_adjacent_grammatical_connector():
    query = '网上到处都有陈景润演讲包括发布会的原文'
    text = '包括发布会的原文已经保存到网页配置资料中。'
    assert admission_decision(query, {'text': text})['decision'].startswith('rejected')
    assert apply_relevance_policy(query, [{'text': text}])[0] == []


_SYNTHETIC_CASES = json.loads((Path(__file__).with_name('fixtures') / 'ep51-synthetic-replies.json').read_text())['cases']


@pytest.mark.parametrize('case', _SYNTHETIC_CASES, ids=lambda case: case['message_id'])
def test_synthetic_reply_keeps_task_content_and_removes_cross_task_rows(case):
    text = extract_user_request(case['prompt'])
    assert 'questionItemId' not in text and 'request_user_input_async' not in text
    assert set(row['id'] for row in case['candidates'] if admission_decision(
        case['prompt'], row)['decision'].startswith('qualified')) == set(case['expected_ids'])
    assert set(row['id'] for row in apply_relevance_policy(
        case['prompt'], case['candidates'])[0]) == set(case['expected_ids'])


@pytest.mark.parametrize('query,text', [
    ('重新用Lecture加工听众就业内容', 'Steam 初始化失败，GameAssembly.dll 以 Collecting from unknown thread 中断。'),
    ('完善Lecture和Skill的受众吸引力', '运行全部单元测试，涵盖test_fixture_state_machine模块。'),
])
def test_latin_fragment_inside_an_unrelated_identifier_is_not_an_independent_anchor(query, text):
    assert admission_decision(query, {'text': text})['decision'].startswith('rejected')


def test_verbose_recall_query_keeps_the_person_in_its_source_slot():
    query = '为优化lecture skill寻找并阅读了哪些青岚整场演讲实录？现在要看那几篇的原文。只核对实际找到的场次、标题、保存文本的位置和全文状态，不查青岚一般资料。'
    related = {'id': 'source', 'text': '青岚演讲实录《星光与远航》全文已保存在演讲研究资料归档。'}
    unrelated = {'id': 'other', 'text': '先核对配置语义与状态闭环，再核对保存的标题和资料。'}
    assert [row['id'] for row in apply_relevance_policy(query, [related, unrelated])[0]] == ['source']
    assert admission_decision(query, related)['decision'].startswith('qualified')
    assert admission_decision(query, unrelated)['decision'].startswith('rejected')


def test_synthetic_recall_results_do_not_answer_requested_source():
    case = json.loads((Path(__file__).with_name('fixtures') / 'ep51-synthetic-recall.json').read_text())
    assert apply_relevance_policy(case['query'], case['candidates'])[0] == []
    assert all(admission_decision(case['query'], row)['decision'].startswith('rejected') for row in case['candidates'])


@pytest.mark.parametrize('subject', ['陈景润', '钱学森', '李政道'])
def test_coordinated_source_owners_are_alternatives_without_requiring_all_in_one_record(subject):
    query = '你找找陈景润、钱学森、李政道一些讲座完整的演讲全文先'
    row = {'text': f'{subject}的演讲全文已经归档，包含完整讲座和出处。'}
    assert len(apply_relevance_policy(query, [row])[0]) == 1
    assert admission_decision(query, row)['decision'].startswith('qualified')


@pytest.mark.parametrize('query,text', [
    ('请找一下陈景润的演讲全文', '陈景润的演讲全文已存档。'),
    ('我想看看陈景润的演讲原文', '陈景润的演讲原文已存档。'),
    ('看陈景润的演讲原文', '陈景润的演讲原文已存档。'),
    ('麻烦展示陈景润的演讲全文', '陈景润的演讲全文已存档。'),
    ('继续制作演讲稿，先找原文再写大纲', '先找原文再写大纲，完整保留论点。'),
])
def test_request_mood_is_not_an_owner_and_unknown_owner_does_not_block_methods(query, text):
    assert admission_decision(query, {'text': text})['decision'].startswith('qualified')
    assert len(apply_relevance_policy(query, [{'text': text}])[0]) == 1


@pytest.mark.parametrize('query,text', [
    ('请看陈景润的演讲原文', '陈景润的演讲原文已存档。'),
    ('找下陈景润的演讲原文', '陈景润的演讲原文已存档。'),
    ('请看李白的文章全文', '李白的文章全文已存档。'),
    ("Read Ada Lovelace's lecture transcript", "Ada Lovelace's lecture transcript is archived."),
    ("Could You Find Ada Lovelace's lecture transcript", "Ada Lovelace's lecture transcript is archived."),
    ("Read Ada Lovelace's lecture transcript", 'Ada Lovelace lecture transcript is in the source archive.'),
    ("Could You Find Ada Lovelace's lecture transcript", 'Ada Lovelace lecture transcript is in the source archive.'),
])
@pytest.mark.parametrize('engine', ['legacy', 'modern'])
def test_review_second_round_source_owner_survives_unknown_request_mood(engine, query, text):
    if engine == 'legacy':
        assert admission_decision(query, {'text': text})['decision'].startswith('qualified')
    else:
        assert len(apply_relevance_policy(query, [{'text': text}])[0]) == 1


@pytest.mark.parametrize('query,text', [
    ('请看陈景润的演讲原文', '钱学森的演讲原文已存档。'),
    ('找下陈景润的演讲原文', '钱学森的演讲原文已存档。'),
    ('请看李白的文章全文', '杜甫的文章全文已存档。'),
    ("Read Ada Lovelace's lecture transcript", "Grace Hopper's lecture transcript is archived."),
    ("Could You Find Ada Lovelace's lecture transcript", "Grace Hopper's lecture transcript is archived."),
])
def test_unknown_request_mood_does_not_admit_a_different_explicit_source_owner(query, text):
    assert admission_decision(query, {'text': text})['decision'].startswith('rejected')
    assert apply_relevance_policy(query, [{'text': text}])[0] == []


def test_english_named_source_request_preserves_a_concrete_transferable_source_procedure():
    query = "Read Ada Lovelace's lecture transcript"
    row = {'text': 'For lecture transcripts, first verify the event and title, then transcribe the complete video and record source links.'}
    assert admission_decision(query, row)['decision'].startswith('qualified')
    assert len(apply_relevance_policy(query, [row])[0]) == 1


@pytest.mark.parametrize('query,text', [
    ('请看陈景润的演讲原文', '陈景润在北京的演讲原文已归档。'),
    ('请看陈景润的演讲原文', '陈景润发表演讲，原文已归档。'),
    ('请看陈景润的演讲原文', '陈景润曾在北京发表长篇演讲，他的原文已归档。'),
    ('请看李白的文章全文', '李白在长安写文章，他的全文已经整理。'),
    ("Read Ada Lovelace's lecture transcript", 'Ada Lovelace delivered the lecture in London; the transcript is archived.'),
    ("Read Ada Lovelace's lecture transcript", 'Ada Lovelace delivered a long lecture in London. Her transcript is archived.'),
    ("Read Plato's lecture transcript", 'Plato delivered the lecture in Athens; its transcript is archived.'),
])
@pytest.mark.parametrize('engine', ['legacy', 'modern'])
def test_source_relation_can_be_expressed_in_natural_clauses(engine, query, text):
    if engine == 'legacy':
        assert admission_decision(query, {'text': text})['decision'].startswith('qualified')
    else:
        assert len(apply_relevance_policy(query, [{'text': text}])[0]) == 1
