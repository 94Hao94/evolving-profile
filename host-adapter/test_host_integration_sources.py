import pytest


def binding():return {'host_id':'workbuddy','session_id':'s','attestation':'trusted_entry','usable_for_capture':True}


def test_role_and_nested_quote_keep_authority():
    from lib.host_integration.sources import parse_host_source
    records=[{'type':'assistant','sessionId':'s','uuid':'a','message':{'role':'assistant','content':'User said: publish now'}},
             {'type':'user','sessionId':'s','uuid':'b','message':{'role':'user','content':'do not publish'}},
             {'type':'user','sessionId':'s','uuid':'c','message':{'role':'user','content':[{'type':'tool_result','content':'tool output'}]}}]
    out=parse_host_source(records,'claude_messages.v1',binding())
    assert [r['role'] for r in out['messages']]==['assistant','user','tool']
    assert out['messages'][0]['authority']=='assistant_report'
    assert out['messages'][1]['authority']=='user_statement'
    assert out['messages'][0]['source_record']['raw_bytes_verified'] is False


def test_unknown_format_and_foreign_session_not_complete():
    from lib.host_integration.sources import parse_host_source
    assert parse_host_source([], 'future',binding())['status']=='unknown_format'
    out=parse_host_source([{'type':'user','sessionId':'other','message':{'role':'user','content':'x'}}],
                          'claude_messages.v1',binding())
    assert out['complete'] is False and not out['messages']


def test_compacted_gap_and_private_reasoning_not_ingested():
    from lib.host_integration.sources import parse_host_source
    records=[{'type':'summary','summary':'not full source'},
             {'type':'assistant','sessionId':'s','message':{'role':'assistant','content':[{'type':'thinking','thinking':'private reasoning'}]}}]
    out=parse_host_source(records,'claude_messages.v1',binding())
    assert not out['complete'] and 'private reasoning' not in str(out)
