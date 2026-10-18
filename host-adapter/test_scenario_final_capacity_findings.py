import json
import pytest
from lib.scenario_coverage_contract import canonical
from lib.scenario_coverage_provider import ConfiguredCoverageProvider
from lib.scenario_hierarchical_review import execute_review
from lib.scenario_hierarchical_transport import fits_request
from test_scenario_hierarchical_review import request,budget,accepted
from test_scenario_hierarchical_end_to_end import setup,controlled,corrupt_source
from test_scenario_review_partial import run


def test_actual_http_bytes_obey_the_accepted_wire_bound(tmp_path):
    sent=[];req=request()
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return json.dumps({'choices':[{'message':{'content':json.dumps(accepted(req)['result'])}}],
            'usage':{'total_tokens':40}}).encode()
    def opener(wire,**kwargs):sent.append(wire.data);return Response()
    provider=ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid',
        'EVOLVING_PROFILE_API_LLM_API_KEY':'not-real'},opener=opener)
    req['limits']['partition_input_tokens']=len(canonical(provider.request_envelope(req)))
    assert fits_request(req,provider)
    out=execute_review(req,provider,budget(tmp_path),source_current=lambda:True,authorize_request=lambda:None)
    assert out['status']=='reviewed'
    assert len(sent)==1 and len(sent[0])<=req['limits']['partition_input_tokens']
    assert json.loads(sent[0])==provider.request_envelope(req)


@pytest.mark.parametrize('flag',['intent_sufficient','conditions_preserved'])
def test_legacy_explicit_semantic_veto_never_enters_format_reselection(tmp_path,flag):
    state,store,s,parts,settings,b=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        v=base(req)
        if req['stage']=='extract':
            v['result'][flag]=False
            corrupt_source(v['result']['proposal']['items'][0])
        return v
    result=run(state,s,parts,settings,b,provider)
    assert [c['stage'] for c in calls]==['extract']
    assert result['status']=='intent_gap' and not result['published']
