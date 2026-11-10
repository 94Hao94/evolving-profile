import json


def test_personal_record_index_extracts_contact_identity_and_name(tmp_path):
    from lib.personal_records import record_messages, search

    result = record_messages([
        {'role':'user','content':'联系人：张三，电话 13812345678，身份证 110101199001011234，邮箱 zhangsan@example.com', 'source_record': {'message_id':'m1'}},
    ], session_id='s1', turn_id='t1', host_id='codex', transcript_path='/tmp/t.jsonl', root=tmp_path)

    assert result['created'] == 4
    found = search('张三', root=tmp_path)
    assert found['returned_count'] == 4
    assert all(row['source']['session_id'] == 's1' for row in found['records'])


def test_personal_record_index_is_atomic_and_deduplicated(tmp_path):
    from lib.personal_records import record_messages, search

    message = {'role':'user','content':'姓名：李四，手机：13912345678'}
    assert record_messages([message], session_id='s', turn_id='t', root=tmp_path)['created'] == 2
    assert record_messages([message], session_id='s', turn_id='t', root=tmp_path)['created'] == 0
    data=json.loads((tmp_path/'host-integrations/personal-records.json').read_text())
    assert len(data['records']) == 2
    assert search('13912345678', root=tmp_path)['returned_count'] == 2


def test_personal_record_index_rejects_label_phrases_and_normalizes_email(tmp_path):
    from lib.personal_records import record_messages, search

    result = record_messages([
        {'role':'user','content':'姓名：项目；联系人：自动推送；邮箱liyuping0304@163.com；姓名：肖俊生'},
    ], root=tmp_path)

    assert result['created'] == 2
    assert search('项目', root=tmp_path)['returned_count'] == 0
    found = search('肖俊生', root=tmp_path)
    assert found['returned_count'] == 2
    assert sum(row['field'] == 'person_name' for row in found['records']) == 1
    email_found = search('liyuping0304@163.com', root=tmp_path)
    assert email_found['returned_count'] == 2
    assert sum(row['field'] == 'email' for row in email_found['records']) == 1
    assert search('邮箱liyuping0304@163.com', root=tmp_path)['returned_count'] == 0


def test_multiple_people_do_not_share_unbound_contacts(tmp_path):
    from lib.personal_records import record_messages, search

    record_messages([
        {'role':'user','content':'姓名：肖俊生，姓名：马木尔，电话：13812345678'},
    ], root=tmp_path)

    assert search('肖俊生', root=tmp_path)['returned_count'] == 1
    assert search('马木尔', root=tmp_path)['returned_count'] == 1
    assert search('13812345678', root=tmp_path)['returned_count'] == 1


def test_structured_person_blocks_bind_only_their_own_fields(tmp_path):
    from lib.personal_records import record_messages, search

    record_messages([
        {'role':'user','content':'张三\n18045032390\n23092119880316021X\n\n李鹤\n15602150501\n120106198408155514\n\n车牌：津AFP8022'},
    ], root=tmp_path)

    liu = search('张三', root=tmp_path)
    he = search('李鹤', root=tmp_path)
    assert {row['value'] for row in liu['records']} == {'张三', '18045032390', '23092119880316021X'}
    assert {row['value'] for row in he['records']} == {'李鹤', '15602150501', '120106198408155514'}
    assert search('津AFP8022', root=tmp_path)['returned_count'] == 1


def test_landline_and_plate_are_captured(tmp_path):
    from lib.personal_records import record_messages, search

    result = record_messages([
        {'role':'user','content':'姓名：李玉平，公司：天津华科智慧科技集团，固定电话022-23784162，手机号18722665035，车牌津AFP8022'},
    ], root=tmp_path)
    assert result['created'] == 4
    assert search('022-23784162', root=tmp_path)['returned_count'] == 4

