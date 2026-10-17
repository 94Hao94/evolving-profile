import copy
import json
import uuid

import pytest

from lib.context_incremental import ContextIncremental, process_summary
from lib.context_summary import read_context_index
from lib.memory_recovery_scenario import MAX_COVERAGE_INPUT_CHARS, source_coverage_review_prompt
from lib.scenario_episodes import partition_source, validate_episode_bundle
from lib.scenario_model import deterministic_source_state_draft
from lib.scenario_review_catalog import review_catalog, review_transport
from test_context_incremental import rollout
from test_memory_recovery_scenario import fixture

CONFIG={'EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid',
        'EVOLVING_PROFILE_API_LLM_API_KEY':'test', 'EVOLVING_PROFILE_API_LLM_MODEL':'fixture'}


def test_impossible_mandatory_source_budget_defers_before_any_provider_and_keeps_raw(tmp_path,monkeypatch):
    text=''.join(f'保留编号{i}的完整原始条件。' for i in range(1800))
    assert len(text)<60000
    sid=str(uuid.uuid4());path=rollout(tmp_path/'sessions',sid,text=text)
    raw_before=path.read_bytes()
    p=ContextIncremental(tmp_path/'state',tmp_path/'sessions');p.discover(now=100)
    def forbidden(*args,**kwargs):raise AssertionError('Provably impossible review reached a paid stage')
    monkeypatch.setattr('lib.scenario_model.request_episode_bundle',forbidden)
    result=p.run_once(CONFIG,now=200)
    assert result['status']=='waiting_source'
    assert result['error_code']=='automated_source_coverage_budget_exceeded'
    assert result['failure_detail']['reason']=='mandatory_source_layer_budget_exceeded'
    assert result['failure_detail']['lower_bound_chars']>MAX_COVERAGE_INPUT_CHARS
    assert result['failure_detail']['input_char_limit']==MAX_COVERAGE_INPUT_CHARS
    assert result['provider_calls']==0 and result['raw_fallback_available'] is True
    assert path.read_bytes()==raw_before
    assert json.loads(path.read_text().splitlines()[-1])['payload']['content'][0]['text']==text
    row=read_context_index(p.index)['sessions'][0]
    assert row['status']=='raw_available_summary_waiting_source'
    assert row['summary_kind']=='not_yet_generated'
    assert p.claim(now=1000) is None


def test_source_only_lower_bound_is_below_real_prompt_for_different_legal_bundles(tmp_path):
    from lib import scenario_review_catalog as catalog_module
    bound=getattr(catalog_module,'mandatory_source_review_lower_bound',None)
    assert bound is not None,'Missing shared source-only mandatory transport bound'
    _,_,source,bundle,_=fixture(tmp_path)
    alternate=copy.deepcopy(bundle);part=partition_source(source,[])[0]
    draft=deterministic_source_state_draft({**source,'messages':part['_messages'],'source_revision':part['source_revision']})
    alternate['episodes']=[{**{k:v for k,v in part.items() if k!='_messages'},'draft':draft,
                           'title':draft['state']['subject']['text'],'title_authority':'navigation_label_not_verified_fact'}]
    alternate['boundary_decisions'][0]['decision']='same_episode'
    for candidate in [bundle,validate_episode_bundle(source,alternate)]:
        catalog=review_catalog(source,candidate);transport=review_transport(source,candidate,catalog)
        fixed={'messages':transport['messages'],'review_selection_catalog':{
            'source_quotes':transport['review_selection_catalog']['source_quotes']}}
        assert bound(source)==len(json.dumps(fixed,ensure_ascii=False))
        assert bound(source)<=len(source_coverage_review_prompt(source,candidate,catalog))
    assert bound({'status':'source_missing','messages':[]}) is None
    assert bound({'status':'complete','messages':[]}) is None


def test_short_and_unknown_inputs_are_not_incorrectly_budget_rejected(tmp_path,monkeypatch):
    _,_,source,bundle,review=fixture(tmp_path);calls=[]
    def draft(*args,**kwargs):calls.append('draft');return bundle
    def episode_review(*args,**kwargs):calls.append('episode_review');return review
    def coverage(*args,**kwargs):calls.append('coverage');return {'fixture':'coverage'}
    def publish(*args,**kwargs):calls.append('publish');return {'status':'fixture_reached_publication_gate'}
    monkeypatch.setattr('lib.scenario_model.request_episode_bundle',draft)
    monkeypatch.setattr('lib.scenario_model.request_episode_bundle_review',episode_review)
    monkeypatch.setattr('lib.memory_recovery_scenario.request_source_coverage_review',coverage)
    monkeypatch.setattr('lib.memory_recovery_scenario.publish_automated_session',publish)
    result=process_summary(source,{},tmp_path,CONFIG)
    assert result['status']=='fixture_reached_publication_gate'
    assert calls==['draft','episode_review','coverage','publish']
    unknown={'status':'source_missing','messages':[]}
    assert process_summary(unknown,{},tmp_path,CONFIG)['status']=='fixture_reached_publication_gate'
