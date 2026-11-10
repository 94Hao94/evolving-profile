"""Background repair is one additional unreviewed draft, never cached acceptance."""
import copy
import json

import pytest

from lib.context_incremental import process_summary
from lib.context_summary import build_session_context
from lib.memory_recovery_scenario import CoverageError
from lib.scenario_model import fingerprint_draft, fingerprint_episode_bundle
from lib.scenario_state_v3 import validate_state_draft
from test_memory_recovery_scenario import fixture, coverage

CONFIG={'EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid',
        'EVOLVING_PROFILE_API_LLM_API_KEY':'test','EVOLVING_PROFILE_API_LLM_MODEL':'fixture'}


def pipeline(tmp_path,monkeypatch,*,failures=1,reason='user_intent_field_attribution_invalid',location=None,
             checkpoint=False,review_rejected=False,change_source=False):
    from lib import scenario_model, memory_recovery_scenario
    root,path,source,bundle,old_review=fixture(tmp_path)
    initial_sha=fingerprint_episode_bundle(bundle);events=[];seen=[]
    config=dict(CONFIG)
    if checkpoint:config['_scenario_checkpoint_root']=tmp_path/'checkpoints'
    def generate(*args,**kwargs):events.append(('generate',initial_sha));return copy.deepcopy(bundle)
    def review(src,current,**kwargs):
        sha=fingerprint_episode_bundle(current);events.append(('review',sha));seen.append(copy.deepcopy(current))
        result=copy.deepcopy(old_review);result['bundle_sha256']=sha
        if review_rejected:result['status']='model_review_rejected'
        for out,episode in zip(result['episode_reviews'],current['episodes']):out['draft_sha256']=fingerprint_draft(episode['draft'])
        return result
    counter=0
    def audit(src,current,**kwargs):
        nonlocal counter
        counter+=1;events.append(('coverage',fingerprint_episode_bundle(current)))
        if counter<=failures:
            if change_source:path.write_text(path.read_text().replace('请编制项目甲方案','已经更改用户请求'))
            raise CoverageError(reason,location=location if location is not None else {'message_ref':'m1','intent_index':0})
        return coverage(src,current)
    def state(local,**kwargs):
        events.append(('repair',kwargs['repair_context']['focus_message_ids']))
        if checkpoint:
            indexes=list((tmp_path/'checkpoints').rglob('index.json'))
            assert indexes and all(json.loads(p.read_text())['status']=='invalidated' for p in indexes)
        draft=copy.deepcopy(bundle['episodes'][0]['draft']['state'])
        draft['goal']['text']='完成项目甲方案编制'
        return validate_state_draft(local,draft,model='fresh-generator')
    actual_publish=memory_recovery_scenario.publish_automated_session
    def publish(row,src,current,checked,audit,session_root):
        sha=fingerprint_episode_bundle(current);events.append(('publish',sha))
        assert checked['bundle_sha256']==audit['bundle_sha256']==sha
        return actual_publish(row,src,current,checked,audit,session_root)
    monkeypatch.setattr(scenario_model,'request_episode_bundle',generate)
    monkeypatch.setattr(scenario_model,'request_episode_bundle_review',review)
    monkeypatch.setattr(scenario_model,'request_session_state_draft',state)
    monkeypatch.setattr(memory_recovery_scenario,'request_source_coverage_review',audit)
    monkeypatch.setattr(memory_recovery_scenario,'publish_automated_session',publish)
    row=build_session_context(source['thread_id'],'project',[],'')
    return source,row,root,config,events,seen,initial_sha


def test_located_failure_repairs_then_reviews_new_fingerprint_before_real_publication(tmp_path,monkeypatch):
    source,row,root,config,events,seen,old=pipeline(tmp_path,monkeypatch,checkpoint=True)
    result=process_summary(source,row,root,config)
    assert result['status']=='episode_directory_ready'
    assert [kind for kind,_ in events]==['generate','review','coverage','repair','review','coverage','publish']
    new=events[-1][1];assert new!=old
    assert events[4][1]==events[5][1]==new
    assert seen[0]['episodes'][1]==seen[1]['episodes'][1]
    assert len([e for e in events if e[0]=='repair'])==1
    assert all(json.loads(p.read_text())['status']=='invalidated' for p in (tmp_path/'checkpoints').rglob('index.json'))


@pytest.mark.parametrize('setting',[0,-5,False,'1',None])
def test_disabled_or_invalid_setting_does_not_generate_repair(tmp_path,monkeypatch,setting):
    source,row,root,config,events,_,_=pipeline(tmp_path,monkeypatch)
    config['_scenario_draft_repair_passes']=setting
    with pytest.raises(CoverageError):process_summary(source,row,root,config)
    assert [kind for kind,_ in events]==['generate','review','coverage']


@pytest.mark.parametrize('setting',[1,2,99])
def test_maximum_one_repair_even_if_coverage_keeps_failing(tmp_path,monkeypatch,setting):
    source,row,root,config,events,_,_=pipeline(tmp_path,monkeypatch,failures=99)
    config['_scenario_draft_repair_passes']=setting
    with pytest.raises(CoverageError) as caught:process_summary(source,row,root,config)
    assert caught.value.reason=='user_intent_field_attribution_invalid'
    assert [kind for kind,_ in events]==['generate','review','coverage','repair','review','coverage']


@pytest.mark.parametrize('reason,location',[
    ('semantic_coverage_rejected',{'message_ref':'m1'}),('user_intent_omitted',{'message_ref':'m1'}),
    ('source_binding_mismatch',{'message_ref':'m1'}),('source_permission_or_eligibility_rejected',{'message_ref':'m1'}),
    ('model_response_invalid',{}),('user_intent_field_attribution_invalid',{}),
    ('user_intent_field_attribution_invalid',{'message_ref':'m99'}),
    ('user_intent_field_attribution_invalid',{'message_ref':'m2'})])
def test_semantic_source_permission_and_untargetable_errors_remain_original(tmp_path,monkeypatch,reason,location):
    source,row,root,config,events,_,_=pipeline(tmp_path,monkeypatch,reason=reason,location=location)
    with pytest.raises(CoverageError) as caught:process_summary(source,row,root,config)
    assert caught.value.reason==reason
    assert [kind for kind,_ in events]==['generate','review','coverage']


@pytest.mark.parametrize('mode',['rejected_episode_review','changed_raw_source'])
def test_failed_review_or_changed_source_cannot_start_a_repair(tmp_path,monkeypatch,mode):
    source,row,root,config,events,_,_=pipeline(tmp_path,monkeypatch,
        review_rejected=mode=='rejected_episode_review',change_source=mode=='changed_raw_source')
    with pytest.raises(CoverageError):process_summary(source,row,root,config)
    assert [kind for kind,_ in events]==['generate','review','coverage']


def test_no_error_pipeline_retains_original_order_and_draft(tmp_path,monkeypatch):
    source,row,root,config,events,seen,old=pipeline(tmp_path,monkeypatch,failures=0)
    assert process_summary(source,row,root,config)['status']=='episode_directory_ready'
    assert [kind for kind,_ in events]==['generate','review','coverage','publish']
    assert all(value==old for kind,value in events)
    assert 'draft_repair' not in seen[0]


def test_runtime_permission_revoked_before_repair_preserves_original_failure(tmp_path,monkeypatch):
    source,row,root,config,events,_,_=pipeline(tmp_path,monkeypatch)
    config['_scenario_state_root']=tmp_path/'state'
    settings=config['_scenario_state_root']/'config/runtime-settings.json';settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({'routing':{'ep_enabled':True},'modules':{'scenario_summary':{'record':False}}}))
    with pytest.raises(CoverageError):process_summary(source,row,root,config)
    assert [kind for kind,_ in events]==['generate','review','coverage']


@pytest.mark.parametrize('mode',['permission_changed','raw_source_changed','provider_budget'])
def test_each_repair_request_guard_and_budget_failure_prevents_further_stages(tmp_path,monkeypatch,mode):
    import io
    import urllib.request
    from lib import scenario_model
    source,row,root,config,events,_,_=pipeline(tmp_path,monkeypatch)
    state_root=tmp_path/'state';config['_scenario_state_root']=state_root
    settings=state_root/'config/runtime-settings.json';settings.parent.mkdir(parents=True)
    allowed={'routing':{'ep_enabled':True},'modules':{'scenario_summary':{'record':True}}}
    settings.write_text(json.dumps(allowed))
    old_state=scenario_model.request_session_state_draft;requests=[]
    def provider(request,timeout):
        requests.append(request)
        if mode=='provider_budget':raise ValueError('provider_budget_exhausted')
        if mode=='permission_changed':
            allowed['modules']['scenario_summary']['record']=False;settings.write_text(json.dumps(allowed))
        if mode=='raw_source_changed':
            path=__import__('pathlib').Path(source['source_files'][0]);path.write_text(path.read_text()+'\n')
        return io.BytesIO(b'fixture')
    def generate_state(local,**kwargs):
        kwargs['opener'](object(),timeout=1)
        return old_state(local,**kwargs)
    monkeypatch.setattr(urllib.request,'urlopen',provider)
    monkeypatch.setattr(scenario_model,'request_session_state_draft',generate_state)
    with pytest.raises(ValueError):process_summary(source,row,root,config)
    assert len(requests)==1
    assert len([event for event in events if event[0]=='review'])==1
    assert len([event for event in events if event[0]=='coverage'])==1
    assert not any(event[0]=='publish' for event in events)


def test_foreign_episode_review_fingerprint_cannot_authorize_repair(tmp_path,monkeypatch):
    from lib import scenario_model
    source,row,root,config,events,_,_=pipeline(tmp_path,monkeypatch)
    original=scenario_model.request_episode_bundle_review
    def review(*args,**kwargs):
        value=original(*args,**kwargs);value['bundle_sha256']='foreign';return value
    monkeypatch.setattr(scenario_model,'request_episode_bundle_review',review)
    with pytest.raises(CoverageError) as caught:process_summary(source,row,root,config)
    assert caught.value.reason=='user_intent_field_attribution_invalid'
    assert [kind for kind,_ in events]==['generate','review','coverage']
