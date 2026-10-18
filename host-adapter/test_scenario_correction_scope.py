import copy
import pytest
from lib.scenario_state_v3 import USER_CLAIM_PROTOCOL, validate_state_draft
from lib.scenario_model import deterministic_source_state_draft, request_episode_bundle
from lib.scenario_episodes import validate_episode_bundle
from test_scenario_state_v3 import source, claim
import test_scenario_episode_model as episode_tests


def state(raw, mid='id1', assistant='id2'):
    return {'subject':claim('Source review',mid),'goal':claim('Preserve source conditions',mid),
            'phase':'assistant_reported','constraints':[claim(raw,mid)],'corrections':[],
            'assistant_reports':[claim('Reported; unverified.',assistant)],'unresolved':[]}


@pytest.mark.parametrize('raw',['不要把采购月份写死，保留后续安排空间。',
                               '不是照搬通用标准，而是针对当前课程。',
                               'AI结果不能直接采信，必须验证。',
                               'Do not publish credentials.'])
def test_initial_negative_condition_preserves_source_valid_provider_constraint(raw):
    original=source([('user',raw),('assistant','Reported; unverified.')])
    supplied=state(raw);before=copy.deepcopy(supplied)
    draft=validate_state_draft(original,supplied,model='fixture',user_claim_protocol=USER_CLAIM_PROTOCOL)
    assert draft['state']['constraints']==[claim(raw,'id1')]
    assert draft['state']['corrections']==[]
    assert supplied==before
    fallback=deterministic_source_state_draft(original)
    assert fallback['state']['constraints']==[claim(raw,'id1')]
    assert fallback['state']['corrections']==[]


def test_new_negative_condition_without_prior_conflict_is_not_forced_into_correction():
    original=source([('user','先做项目方案。'),('assistant','已答复。'),
                     ('user','不要公开凭据。'),('assistant','已记录。')])
    draft=validate_state_draft(original,state('不要公开凭据。','id3','id4'),model='fixture',user_claim_protocol=USER_CLAIM_PROTOCOL)
    assert draft['state']['constraints']==[claim('不要公开凭据。','id3')]
    assert draft['state']['corrections']==[]


def test_repeated_prohibition_is_not_mistaken_for_a_conflicting_prior_permission():
    original=source([('user','不要公开凭据。'),('assistant','已答复。'),
                     ('user','不要公开凭据。'),('assistant','已记录。')])
    draft=validate_state_draft(original,state('不要公开凭据。','id3','id4'),model='fixture',user_claim_protocol=USER_CLAIM_PROTOCOL)
    assert draft['state']['constraints']==[claim('不要公开凭据。','id3')]
    assert draft['state']['corrections']==[]


@pytest.mark.parametrize('earlier',['不要把标题写成采购清单。','如果需要，可以把标题写成采购清单。'])
def test_prior_prohibition_or_conditional_is_not_a_positive_instruction_witness(earlier):
    later='不要把标题写成采购清单，要保留合作方案语气。'
    original=source([('user',earlier),('assistant','已答复。'),('user',later),('assistant','已记录。')])
    draft=validate_state_draft(original,state(later,'id3','id4'),model='fixture',user_claim_protocol=USER_CLAIM_PROTOCOL)
    assert draft['state']['constraints']==[claim(later,'id3')]
    assert draft['state']['corrections']==[]


@pytest.mark.parametrize('earlier',['请解释公开密钥的风险。','我不会公开密钥。','公开密钥的风险很高。',
                                   '是否公开密钥？','“公开密钥。”'])
def test_discussion_negation_question_and_quote_are_not_whole_positive_commands(earlier):
    original=source([('user',earlier),('assistant','已答复。'),('user','不要公开密钥。'),('assistant','已记录。')])
    draft=validate_state_draft(original,state('不要公开密钥。','id3','id4'),model='fixture',user_claim_protocol=USER_CLAIM_PROTOCOL)
    assert draft['state']['constraints']==[claim('不要公开密钥。','id3')]
    assert draft['state']['corrections']==[]


@pytest.mark.parametrize('raw',['如果后面需要，可以改成另一方案。','“更正：不要公开凭据。”'])
def test_conditional_or_quoted_revision_words_remain_uncertain_constraints(raw):
    original=source([('user',raw),('assistant','Reported; unverified.')])
    draft=validate_state_draft(original,state(raw),model='fixture')
    assert draft['state']['constraints']==[claim(raw,'id1')]
    assert draft['state']['corrections']==[]


def test_explicit_later_revision_retains_exact_clause_and_replaces_category():
    original=source([('user','将标题写成采购清单。'),('assistant','已答复。'),
                     ('user','更正：将标题改为合作方案。'),('assistant','已修改。')])
    raw='更正：将标题改为合作方案。'
    draft=validate_state_draft(original,state(raw,'id3','id4'),model='fixture',user_claim_protocol=USER_CLAIM_PROTOCOL)
    assert draft['state']['constraints']==[]
    assert draft['state']['corrections']==[claim(raw,'id3')]


def test_prior_source_contradiction_survives_episode_boundary_without_cross_source_citation():
    original=episode_tests.source([('t1','用中转生图。','已开始。'),
                             ('t2','不用中转生图了。','已换直接生成。')])
    opener,_=episode_tests.EpisodeModelTests().fake_opener({'id3':'new_episode'})
    bundle=request_episode_bundle(original,base_url='https://fixture.invalid',api_key='test',model='fixture',opener=opener)
    latest=bundle['episodes'][1]['draft']
    assert latest['state']['corrections']==[claim('不用中转生图了。','id3')]
    assert all(mid in {'id3','id4'} for row in latest['evidence'] for mid in row['message_ids'])
    assert validate_episode_bundle(original,bundle)['episodes'][1]['draft']['state']==latest['state']
