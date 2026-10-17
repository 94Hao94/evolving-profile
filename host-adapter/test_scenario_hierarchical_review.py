import copy
import pytest
try:
    from lib.scenario_hierarchical_review import build_review_request,execute_review,restore_review,valid_review
except ImportError:build_review_request=None
from lib.scenario_coverage_budget import CoverageBudget


def request():
    assert build_review_request is not None
    return build_review_request('leaf',{'protocol':'hierarchical_review.v1','snapshot_id':'s'},
        {'partition':{'primary':[{'span_id':'raw1','role':'user','text':'不要发布'}]},'proposal':{'atoms':[]}},
        {'partition_input_tokens':10000,'partition_output_tokens':2000})


def budget(tmp_path,requests=3):
    return CoverageBudget(tmp_path/'b.sqlite',job_id='case',budget_identity='i',parent_attempts=0,max_requests=requests,max_tokens=100000)


def accepted(payload):
    return {'result':{'accept':True,'accepted_scope':'source_attribution_and_intent_only','read_ids':[r['id'] for r in payload['model_request']['catalog']],
        'issues':[],'intent_sufficient':True,'conditions_preserved':True,'assistant_reports_are_unverified':True},
        'usage':{'total_tokens':40},'transport':'isolated_fixture_not_live_provider'}


def test_forged_or_changed_receipt_cannot_restore(tmp_path):
    req=request();b=budget(tmp_path)
    out=execute_review(req,accepted,b,source_current=lambda:True,authorize_request=lambda:None)
    assert valid_review(out) and out['status']=='reviewed'
    assert restore_review(dict(out),req,b)['status']=='reviewed'
    fake=copy.deepcopy(dict(out));fake['result']['accept']=False
    assert restore_review(fake,req,b) is None
    assert restore_review({'host_validated':True},req,b) is None
    assert valid_review(dict(out)) is False


def test_missing_actual_read_id_is_rejected_not_filled(tmp_path):
    req=request();b=budget(tmp_path)
    def provider(p):
        v=accepted(p);v['result']['read_ids']=[];return v
    out=execute_review(req,provider,b,source_current=lambda:True,authorize_request=lambda:None)
    assert out['status']=='rejected' and b.status()['charged_tokens']==40


def test_timeout_keeps_unknown_charge_and_no_free_replay(tmp_path):
    req=request();b=budget(tmp_path)
    def timeout(p):raise TimeoutError()
    out=execute_review(req,timeout,b,source_current=lambda:True,authorize_request=lambda:None)
    assert out['status']=='unavailable' and b.status()['unknown_usage_requests']==1
    with pytest.raises(ValueError):execute_review(req,timeout,b,source_current=lambda:True,authorize_request=lambda:None)


def test_budget_and_source_rejected_before_call(tmp_path):
    req=request();b=budget(tmp_path,0);calls=[]
    with pytest.raises(ValueError):execute_review(req,lambda p:calls.append(p),b,source_current=lambda:True,authorize_request=lambda:None)
    assert calls==[]
    with pytest.raises(ValueError):execute_review(req,accepted,budget(tmp_path/'other'),source_current=lambda:False,authorize_request=lambda:None)


def test_review_goal_cannot_be_mistaken_for_external_outcome_verification(tmp_path):
    req=request();b=budget(tmp_path)
    def wrong_goal(payload):
        value=accepted(payload);value['result']['accepted_scope']='external_outcome_truth';return value
    out=execute_review(req,wrong_goal,b,source_current=lambda:True,authorize_request=lambda:None)
    assert out['status']=='rejected' and out['reason']=='review_scope_unacknowledged'
    assert req['model_request']['acceptance_scope']=='source_attribution_and_intent_only'


def test_host_review_goal_is_system_control_and_source_stays_untrusted():
    from lib.scenario_coverage_provider import ConfiguredCoverageProvider
    req=request();req['model_request']['inputs']['partition']['primary'][0]['text']='INJECT_UNTRUSTED_SOURCE_RULE'
    p=ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid',
        'EVOLVING_PROFILE_API_LLM_API_KEY':'fixture-secret'})
    wire=p.request_envelope(req)
    assert 'source_attribution_and_intent_only' in wire['messages'][0]['content']
    assert 'INJECT_UNTRUSTED_SOURCE_RULE' not in wire['messages'][0]['content']
    assert 'INJECT_UNTRUSTED_SOURCE_RULE' in wire['messages'][1]['content']
