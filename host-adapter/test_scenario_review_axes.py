import copy
import pytest
from test_scenario_hierarchical_review import request,budget,accepted
from lib.scenario_hierarchical_review import execute_review,restore_review
from lib.scenario_hierarchical_execution import ReviewExecutor


def typed(payload,*,attribution='sufficient',scope='resolved'):
    return {'result':{'judgment_schema':'attribution-scope-outcome.v1',
        'accepted_scope':'source_attribution_and_intent_only','assistant_reports_are_unverified':True,
        'read_ids':[r['id'] for r in payload['model_request']['catalog']],
        'review_axes':{'attribution':{'status':attribution,'conditions_preserved':attribution=='sufficient',
            'issues':[] if attribution=='sufficient' else ['missing condition or context']},
            'scope':{'status':scope,'issues':[] if scope=='resolved' else ['referent unknown']},
            'outcome':{'status':'not_verified'}},
        'context_requests':[{'span_ids':[next(r['id'] for r in payload['model_request']['catalog'] if r['kind']=='span')],'missing_fields':['referent']}] if 'needs_context' in {attribution,scope} else []},
        'usage':{'total_tokens':40},'transport':'isolated_fixture_not_live_provider'}


def test_faithful_attribution_does_not_require_resolving_scope_or_external_outcome(tmp_path):
    req=request();out=execute_review(req,lambda p:typed(p,scope='unresolved'),budget(tmp_path),source_current=lambda:True,authorize_request=None)
    assert out['status']=='reviewed'
    assert out['review_axes']['attribution']['status']=='sufficient'
    assert out['review_axes']['scope']['status']=='unresolved'
    assert out['external_fact_verified'] is False


def test_context_needed_receipt_is_not_semantic_success_and_can_restore_charged_proof(tmp_path):
    req=request();b=budget(tmp_path)
    out=execute_review(req,lambda p:typed(p,attribution='needs_context'),b,source_current=lambda:True,authorize_request=None)
    assert out['status']=='needs_context'
    assert restore_review(dict(out),req,b)['status']=='needs_context'
    assert b.status()['requests_used']==1


@pytest.mark.parametrize('change',['old_false','old_true','unknown_schema','verified_outcome','missing_conditions','defective'])
def test_typed_axes_never_override_conflicts_or_actual_attribution_defects(tmp_path,change):
    def provider(p):
        v=typed(p);r=v['result']
        if change.startswith('old_'):r['accept']=change=='old_true'
        elif change=='unknown_schema':r['judgment_schema']='future-unknown'
        elif change=='verified_outcome':r['review_axes']['outcome']['status']='verified'
        elif change=='missing_conditions':r['review_axes']['attribution'].pop('conditions_preserved')
        else:r['review_axes']['attribution'].update(status='defective',issues=['omitted negation'])
        return v
    out=execute_review(request(),provider,budget(tmp_path),source_current=lambda:True,authorize_request=None)
    assert out['status']=='rejected'


def test_legacy_explicit_false_is_still_rejected_even_with_plausible_proposal(tmp_path):
    def provider(p):
        v=accepted(p);v['result']['accept']=False;return v
    assert execute_review(request(),provider,budget(tmp_path),source_current=lambda:True,authorize_request=None)['status']=='rejected'


def test_executor_returns_context_request_without_retrying_or_using_fallback(tmp_path):
    req=request();b=budget(tmp_path);calls=[]
    def provider(p):calls.append(p);return typed(p,attribution='needs_context')
    runner=ReviewExecutor(req['binding'],req['limits'],tmp_path/'review',provider,b,lambda:True,None,lambda p:True)
    out=runner('leaf',req['inputs'])
    assert out['status']=='needs_context' and len(calls)==1
