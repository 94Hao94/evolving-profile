from copy import deepcopy
from lib.scenario_hierarchical_review import build_review_request
from lib.scenario_coverage_contract import canonical
from lib.scenario_coverage_provider import ConfiguredCoverageProvider


def test_transport_wire_omits_host_bookkeeping_but_retains_every_primary_and_context_character():
    original={'partition_id':'p'*64,'snapshot_id':'s'*64,'draft_reuse_basis':'opaque-host-data'*1000,
        'reused_from_partition_id':'previous','semantic_task_boundary':'unknown','context_only':'先前原文🙂',
        'primary':[{'span_id':'span1','role':'assistant','sequence':10,'start':4,'end':18,
          'text':'assistant-only正文🙂','transport_span_not_independent_fact':True,'unit_id':'u'*64,'raw_line_sha256':'r'*64}]}
    before=deepcopy(original)
    request=build_review_request('extract',{}, {'partition':original},{'partition_input_tokens':6000,'partition_output_tokens':2000})
    p=ConfiguredCoverageProvider({'EVOLVING_PROFILE_API_LLM_MODEL':'fixture','EVOLVING_PROFILE_API_LLM_BASE_URL':'https://fixture.invalid','EVOLVING_PROFILE_API_LLM_API_KEY':'not-real'})
    assert len(canonical(p.request_envelope(request)))<=6000
    wire=request['model_request']['inputs']['partition']
    assert wire['context_only']=='先前原文🙂'
    assert wire['semantic_task_boundary']=='unknown'
    assert wire['primary']==[{'span_id':'r0','role':'assistant','sequence':10,'start':4,'end':18,
        'text':'assistant-only正文🙂','transport_span_not_independent_fact':True}]
    assert set(wire)=={'primary','context_only','semantic_task_boundary'}
    assert request['inputs']['partition']==before and original==before
