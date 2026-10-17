import copy
from lib.scenario_coverage_incremental import process_coverage_job
from lib.scenario_coverage_store import CoverageStore
from lib.scenario_coverage_partition import partition_snapshot
from lib.scenario_hierarchical_output_recovery import split_failed_partition
from lib.scenario_hierarchical_review import build_review_request,execute_review
from lib.scenario_hierarchical_context import recover_leaf_context
from lib.scenario_coverage_budget import CoverageBudget
from test_scenario_source_codec import source
from test_scenario_coverage_incremental import job
from test_scenario_review_axes import typed


def test_split_child_can_read_omitted_condition_from_same_original_message(tmp_path):
    raw='仅适用于项目甲，以下全部限制也仅针对项目甲。'+'中间资料'*25+'未经确认不得发布。'
    root,_,_=source(tmp_path,text=raw);state=tmp_path/'state'
    result=process_coverage_job(job(),root,{},store_root=state)
    snap=CoverageStore(state/'coverage.sqlite3').read(result['snapshot_id'])
    parent=partition_snapshot(snap,capacity=1800)['partitions'][0]
    child=split_failed_partition(snap,parent,depth=0,additional_windows=0)[1]
    assert '仅适用于项目甲' not in ''.join(s['text'] for s in child['primary'])
    original=copy.deepcopy(child)
    binding={k:snap[k] for k in ('snapshot_id','generation','scope','permission','selection_version','normalization_version')}
    binding['protocol']='hierarchical_review.v1'
    limits={'partition_input_tokens':20000,'partition_output_tokens':2000}
    b=CoverageBudget(state/'context.sqlite3',job_id='split',budget_identity='fixed',parent_attempts=0,max_requests=4,max_tokens=100000)
    req=build_review_request('leaf',binding,{'partition':child,'proposal':{}},limits)
    review=execute_review(req,lambda p:typed(p,attribution='needs_context',scope='needs_context'),b,source_current=lambda:True,authorize_request=None)
    observed=[]
    def executor(stage,inputs):
        observed.extend(inputs.get('context_pages',[]))
        found=any('仅适用于项目甲' in p['text'] for p in inputs.get('context_pages',[]))
        return execute_review(build_review_request(stage,binding,inputs,limits),
            lambda p:typed(p,scope='resolved' if found else 'needs_context'),b,
            source_current=lambda:True,authorize_request=None)
    out=recover_leaf_context(snap,child,{},review,executor=executor,root=state,
        permission_getter=lambda:snap['permission'],provider=typed,limits=limits)
    assert out['stop_reason']=='resolved' and out['model_context_rounds']==1
    assert observed[0]['unit_id']==child['primary'][0]['unit_id']
    assert observed[0]['text']=='仅适用于项目甲，以下全部限制也仅针对项目甲。'+'中间资料'*11+'中间资'
    assert observed[0]['text_offset']+len(observed[0]['text'])==child['primary'][0]['start']
    assert child==original and b.status()['requests_used']==2
