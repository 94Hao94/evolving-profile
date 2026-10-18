import json
import pytest
from lib.scenario_coverage_read import read_coverage_view
from lib.scenario_coverage_incremental import process_coverage_job
from test_scenario_coverage_incremental import job
from test_scenario_source_codec import SID,source


def test_requirement_pages_declare_unread_and_stale_cursor(tmp_path):
    root,path,_=source(tmp_path,text='不要删🙂。'*1000);state=tmp_path/'state'
    process_coverage_job(job(),root,{},store_root=state)
    page=read_coverage_view(state,SID,'requirements',permission=job()['permission'])
    assert page['source_readback'] is False and page['has_unread_requirements'] is True
    assert page['coverage_cursor'] and len(page['requirements'][0]['text'])<6000
    assert page['semantic_review_status']=='not_reviewed'
    later=read_coverage_view(state,SID,'requirements',cursor=page['coverage_cursor'],permission=job()['permission'])
    assert later['requirements'][0]['text_offset']>0
    assert later['has_unread_requirements'] is True
    assert later['all_requirements_in_this_response'] is False
    path.write_bytes(path.read_bytes()+b'{}\n')
    with pytest.raises(ValueError,match='stale'):
        read_coverage_view(state,SID,'requirements',cursor=page['coverage_cursor'],permission=job()['permission'])


def test_scope_permission_and_view_change_cannot_reuse_cursor(tmp_path):
    root,_,_=source(tmp_path,text='不要发布。'*1000);state=tmp_path/'state'
    process_coverage_job(job(),root,{},store_root=state)
    page=read_coverage_view(state,SID,'requirements',permission=job()['permission'])
    with pytest.raises(ValueError):read_coverage_view(state,SID,'relations',cursor=page['coverage_cursor'],permission=job()['permission'])
    with pytest.raises(ValueError):read_coverage_view(state,SID,'requirements',permission={'allowed':False,'version':'p1'})


def test_raw_source_click_returns_actual_body_and_verified_locator(tmp_path):
    root,_,_=source(tmp_path,True);state=tmp_path/'state'
    process_coverage_job(job(),root,{},store_root=state)
    page=read_coverage_view(state,SID,'requirements',permission=job()['permission'])
    raw=read_coverage_view(state,SID,'source',permission=job()['permission'],requirement_id=page['requirements'][0]['requirement_id'])
    assert raw['source_readback'] is True and '不要删除原文件' in raw['raw_source']['text']
    assert raw['raw_source']['read_method']=='verified_decoded_raw_records'
    assert raw['raw_source']['locators'][0]['raw_line_sha256']


def test_source_click_is_exact_record_not_another_message_in_same_turn(tmp_path):
    root,path,_=source(tmp_path,text='early '*4000);state=tmp_path/'state'
    with path.open('a') as f:f.write(json.dumps({'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'ONLY_TARGET'}]}})+'\n')
    outcome=process_coverage_job(job(),root,{},store_root=state)
    inventory=json.loads((state/'inventories'/(outcome['snapshot_id']+'.json')).read_text())
    rid=inventory['requirements']['requirements'][-1]['requirement_id']
    raw=read_coverage_view(state,SID,'source',permission=job()['permission'],requirement_id=rid)
    assert 'ONLY_TARGET' in raw['raw_source']['text'] and 'early early' not in raw['raw_source']['text']
