import copy
import pytest
from test_scenario_hierarchical_end_to_end import setup,controlled,corrupt_source
from test_scenario_review_partial import run
from lib.scenario_hierarchical_store import HierarchicalStore


@pytest.mark.parametrize('supplied_claim',[None,'助手报告完成，外部成果未核验'])
def test_leaf_and_capsule_use_same_effective_assistant_report_text(tmp_path,supplied_claim):
    state,_,s,parts,settings,b=setup(tmp_path);calls=[];base=controlled(calls)
    expected=supplied_claim or '完成（助手自述）'
    def provider(req):
        value=base(req)
        if req['stage']=='extract':
            spans=[span for span in req['model_request']['inputs']['partition']['primary'] if span['role']=='assistant']
            rows=[{'kind':'report','action':'report_completion',
                'source_cards':[span['span_id']]} for span in spans]
            if supplied_claim:
                for row in rows:row['claim']=supplied_claim
            value['result']['proposal']['items']=[r for r in value['result']['proposal']['items'] if r['kind']!='report']+rows
        if req['stage']=='leaf':
            assert req['inputs']['proposal']['assistant_claims'][0]['claim']==expected
        return value
    result=run(state,s,parts,settings,b,provider)
    assert result['status']=='scope_reviewed'
    g=HierarchicalStore(state/'hierarchical/graphs.sqlite3',readonly=True).load_current(s['scope'],s['permission'])['graph']
    assert g['assistant_claims'][0]['claim']==expected
    assert g['assistant_claims'][0]['external_fact_verified'] is False
    if supplied_claim is None:
        import json
        raw=[json.loads(p.read_text()) for p in (state/'hierarchical/reviews').glob('*.json')]
        producer=next(r for r in raw if r['stage']=='extract')
        assert all('claim' not in row for row in producer['provider_response']['result']['proposal']['items'])


def test_single_source_mapping_feedback_repair_reaches_independent_leaf_and_keeps_initial_failure(tmp_path):
    state,store,s,parts,settings,b=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        value=base(req)
        if req['stage']=='extract' and 'validation_feedback' not in req['inputs']:
            corrupt_source(value['result']['proposal']['items'][0])
        return value
    result=run(state,s,parts,settings,b,provider)
    assert result['status']=='scope_reviewed'
    assert [c['stage'] for c in calls]==['extract','extract','leaf','merge']
    feedback=calls[1]['inputs']['validation_feedback']
    assert feedback['errors'] and feedback['previous_request_sha256']
    assert b.status()['requests_used']==4
    graph=HierarchicalStore(state/'hierarchical/graphs.sqlite3',readonly=True).load_current(s['scope'],s['permission'])['graph']
    assert len(graph['format_repairs'])==1
    assert graph['format_repairs'][0]['initial_errors']
    from lib.scenario_hierarchical_read import read_hierarchical_view
    from test_scenario_coverage_incremental import job
    view=read_hierarchical_view(state,job()['session_id'],'overview',cursor=None,permission=s['permission'],expected_scope=s['scope'],requirement_id=None)
    assert view['processing_diagnostics']['format_reselections']==1
    assert view['processing_diagnostics']['repair_model_calls']==1
    assert view['processing_diagnostics']['source_scope_reduced'] is False


def test_repeated_mapping_failure_has_only_one_charged_reselection_and_no_leaf(tmp_path):
    state,store,s,parts,settings,b=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        value=base(req)
        if req['stage']=='extract':corrupt_source(value['result']['proposal']['items'][0])
        return value
    result=run(state,s,parts,settings,b,provider)
    assert [c['stage'] for c in calls]==['extract','extract']
    assert result['status']=='intent_gap' and not result['published']


def test_semantic_veto_does_not_trigger_format_reselection(tmp_path):
    state,store,s,parts,settings,b=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        value=base(req);value['result']['accept']=False;return value
    result=run(state,s,parts,settings,b,provider)
    assert [c['stage'] for c in calls]==['extract']
    assert result['status']=='intent_gap' and not result['published']


def test_mapping_feedback_identifies_all_roles_empty_quotes_and_uncovered_source_without_rewriting():
    from lib.scenario_hierarchical_extraction import mapping_feedback
    # These are diagnostic inputs, not source validation bypasses. Full tests
    # below exercise actual immutable source and the ordinary validator.
    from test_scenario_intent_atoms import fixture
    from tempfile import TemporaryDirectory
    from pathlib import Path
    with TemporaryDirectory(dir='/private/tmp') as temp:
        snap,part,proposal=fixture(Path(temp),'资料路径.pdf；只生成草稿🙂，不要发布。')
        user=part['primary'][0];assistant=next(p for p in part['primary'] if p['role']=='assistant')
        first=proposal['atoms'][0];first['source_refs']=[{'span_id':user['span_id'],'quote':'只生成草稿🙂，不要发布。'}]
        wrong=copy.deepcopy(first);wrong['source_refs']=[{'span_id':assistant['span_id'],'quote':assistant['text']}]
        proposal['atoms'].append(wrong)
        proposal['residuals']=[{'reason':'non_substantive','source_refs':[{'span_id':user['span_id'],'quote':''}]}]
        original=copy.deepcopy(proposal)
        feedback=mapping_feedback(snap,part,proposal,['atom_authority_or_role'])
        assert {'atom_authority_or_role','atom_quote_invalid','intent_character_gap'}<=set(feedback['errors'])
        assert feedback['uncovered_primary_ranges']==[{'span_id':user['span_id'],'start':0,'end':9}]
        assert proposal==original


def test_format_reselection_obeys_parent_budget_without_free_third_call(tmp_path):
    from lib.scenario_coverage_budget import CoverageBudget
    state,store,s,parts,settings,_=setup(tmp_path);calls=[];base=controlled(calls)
    budget=CoverageBudget(state/'tiny.sqlite3',job_id='tiny',budget_identity=s['semantic_budget_identity'],
        parent_attempts=1,max_requests=1,max_tokens=100000)
    def provider(req):
        value=base(req);corrupt_source(value['result']['proposal']['items'][0]);return value
    result=run(state,s,parts,settings,budget,provider)
    assert len(calls)==1 and budget.status()['requests_used']==1
    assert result['status']=='budget_paused' and not result['published']


def test_source_change_after_initial_extraction_stops_reselection(tmp_path):
    state,store,s,parts,settings,b=setup(tmp_path);calls=[];base=controlled(calls)
    def provider(req):
        value=base(req);corrupt_source(value['result']['proposal']['items'][0])
        with open(s['location']['path'],'a') as f:f.write('{}\n')
        return value
    result=run(state,s,parts,settings,b,provider)
    assert len(calls)==1 and not result['published']
    assert result['reason']=='source_or_permission_changed'


def test_repair_feedback_does_not_resend_redundant_diagnostic_metadata(tmp_path):
    import json
    from lib.scenario_coverage_contract import canonical
    from lib.scenario_coverage_provider import ConfiguredCoverageProvider
    from lib.scenario_hierarchical_review import build_review_request
    from lib.scenario_hierarchical_execution import ReviewExecutor
    from lib.scenario_hierarchical_extraction import extract_with_feedback
    state,store,s,parts,settings,b=setup(tmp_path);sent=[];calls=[];base=controlled(calls);part=parts['partitions'][0]
    class Response:
        def __init__(self,data):self.data=data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return self.data
    def opener(wire,**kwargs):
        data=json.loads(wire.data);p=json.loads(data['messages'][1]['content']);sent.append((wire.data,p))
        value=base({'stage':p['stage'],'model_request':p})
        if len(sent)==1:
            alias=p['inputs']['partition']['primary'][0]['span_id']
            value['result']['proposal']['residuals']=[{'reason':'non_substantive','source_refs':[{'span_id':alias,'quote':''}]}]
        return Response(json.dumps({'choices':[{'message':{'content':json.dumps(value['result'])}}],'usage':{'total_tokens':80}}).encode())
    p=ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid','EVOLVING_PROFILE_API_LLM_API_KEY':'not-real'},opener=opener)
    limits=settings['limits'];binding={};initial=build_review_request('extract',binding,{'partition':part},limits)
    limits['partition_input_tokens']=len(canonical(p.request_envelope(initial)))+500
    executor=ReviewExecutor(binding,limits,state/'feedback-http',p,b,lambda:True,lambda:None,lambda p:True)
    extraction,proposal,checked,repairs=extract_with_feedback(s,part,executor)
    assert checked['errors']==[] and len(sent)==2 and b.status()['requests_used']==2
    assert all(len(body)<=limits['partition_input_tokens'] for body,_ in sent)
    feedback=sent[1][1]['inputs']['validation_feedback']
    assert feedback['errors']==['atom_quote_invalid'] and feedback['previous_response_sha256']
    assert repairs[0]['feedback']['empty_primary_spans'] is not None
