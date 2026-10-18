import io,json
import pytest
from lib.scenario_coverage_provider import ConfiguredCoverageProvider
from lib.scenario_hierarchical_review import execute_review
from test_scenario_hierarchical_review import request,budget


def test_complete_http_usage_is_settled_even_when_model_output_is_truncated(tmp_path):
    raw=json.dumps({'choices':[{'finish_reason':'length','message':{'content':'{"unfinished":'}}],
        'usage':{'prompt_tokens':300,'completion_tokens':2000,'total_tokens':2300}}).encode()
    p=ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid','EVOLVING_PROFILE_API_LLM_API_KEY':'not-real'},
        opener=lambda *a,**kw:io.BytesIO(raw))
    b=budget(tmp_path);out=execute_review(request(),p,b,source_current=lambda:True,authorize_request=lambda:None)
    assert out['status']=='unavailable' and out['reason']=='provider_capacity_failed'
    assert b.status()['requests_used']==1 and b.status()['charged_tokens']==2300
    assert b.status()['unknown_usage_requests']==0
    assert out['result'] is None and out['response_sha256']
    assert out['provider_response']['response_wire_sha256']


@pytest.mark.parametrize('choices',[[{'finish_reason':'stop','message':{'content':'not JSON'}}],[],[None]])
def test_malformed_inner_model_json_keeps_known_usage_but_cannot_be_reviewed(tmp_path,choices):
    raw=json.dumps({'choices':choices,
        'usage':{'total_tokens':71}}).encode()
    p=ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid','EVOLVING_PROFILE_API_LLM_API_KEY':'not-real'},
        opener=lambda *a,**kw:io.BytesIO(raw))
    b=budget(tmp_path);out=execute_review(request(),p,b,source_current=lambda:True,authorize_request=lambda:None)
    assert out['status']=='unavailable' and out['result'] is None
    assert b.status()['charged_tokens']==71 and b.status()['unknown_usage_requests']==0
