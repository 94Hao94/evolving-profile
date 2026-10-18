import copy
from lib.scenario_hierarchical_review import build_review_request,execute_review,restore_review
from test_scenario_hierarchical_review import budget,request


def proposal_request():
    return build_review_request('extract',{'protocol':'hierarchical_review.v1','snapshot_id':'s'},
        {'partition':{'primary':[{'span_id':'raw1','role':'user','text':'不要发布'}]}},
        {'partition_input_tokens':10000,'partition_output_tokens':2000})


def test_producer_needs_no_self_acceptance_and_cache_stays_only_proposed(tmp_path):
    req=proposal_request();b=budget(tmp_path)
    response={'result':{'proposal':{'atoms':[],'residuals':[],'assistant_claims':[]},'context_requests':[]},
              'usage':{'total_tokens':40}}
    out=execute_review(req,lambda _:response,b,source_current=lambda:True,authorize_request=None)
    assert out['status']=='proposed' and out['review_axes'] is None
    assert restore_review(dict(out),req,b)['status']=='proposed'
    forged=copy.deepcopy(dict(out));forged['status']='reviewed'
    assert restore_review(forged,req,b) is None
    assert restore_review(dict(out),request(),b) is None


def test_proposal_without_independent_judgment_cannot_pass_leaf(tmp_path):
    response={'result':{'proposal':{'atoms':[],'residuals':[],'assistant_claims':[]}},'usage':{'total_tokens':40}}
    out=execute_review(request(),lambda _:response,budget(tmp_path),source_current=lambda:True,authorize_request=None)
    assert out['status']=='rejected'


def test_malformed_proposal_shape_rejected_before_any_leaf(tmp_path):
    response={'result':{'proposal':{'atoms':{},'residuals':[],'assistant_claims':[]}},'usage':{'total_tokens':40}}
    out=execute_review(proposal_request(),lambda _:response,budget(tmp_path),source_current=lambda:True,authorize_request=None)
    assert out['status']=='rejected' and out['reason']=='proposal_fields'
