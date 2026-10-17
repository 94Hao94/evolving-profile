"""An entry hash cannot certify its unchanged-looking deployed code tree."""
from pathlib import Path
import os
import source_of_truth_audit as module


def audit(source,runtime):
    fn=getattr(module,'audit_runtime_code',None)
    assert callable(fn),'The existing source-of-truth auditor lacks deployed code-tree verification'
    return fn(source,runtime,components=['host-adapter'])


def fixture(tmp_path):
    source=tmp_path/'source';runtime=tmp_path/'runtime'
    for root in [source,runtime]:
        (root/'host-adapter/lib').mkdir(parents=True)
        (root/'host-adapter/entry.py').write_text('raise RuntimeError("must never execute inspected code")\n')
        (root/'host-adapter/lib/budget.py').write_text('full=12000\n')
    return source,runtime


def test_complete_code_tree_matches_without_execution(tmp_path):
    a,b=fixture(tmp_path);result=audit(a,b)
    assert result['status']=='matched'
    assert result['coverage']=='declared_production_python_trees'
    assert len(result['files'])==2


def test_stale_budget_is_detected_even_when_entry_matches(tmp_path):
    a,b=fixture(tmp_path);(b/'host-adapter/lib/budget.py').write_text('full=4000\n')
    result=audit(a,b)
    assert result['status']=='drift'
    assert result['mismatches']==[{'path':'host-adapter/lib/budget.py','reason':'content_changed'}]


def test_missing_deployed_module_is_not_zero_or_healthy(tmp_path):
    a,b=fixture(tmp_path);(b/'host-adapter/lib/budget.py').unlink()
    assert audit(a,b)['mismatches']==[{'path':'host-adapter/lib/budget.py','reason':'missing_runtime_file'}]


def test_runtime_only_package_that_can_shadow_a_module_is_not_ignored(tmp_path):
    a,b=fixture(tmp_path);(b/'host-adapter/entry').mkdir()
    (b/'host-adapter/entry/__init__.py').write_text('raise RuntimeError("stale shadow")\n')
    result=audit(a,b)
    assert result['status']=='drift'
    assert result['mismatches']==[{'path':'host-adapter/entry/__init__.py','reason':'unexpected_runtime_file'}]


def test_test_and_cache_artifacts_do_not_become_deployed_code_requirements(tmp_path):
    a,b=fixture(tmp_path)
    (a/'host-adapter/test_fixture.py').write_text('unshipped test\n')
    (b/'host-adapter/__pycache__').mkdir();(b/'host-adapter/__pycache__/noise.py').write_text('generated\n')
    assert audit(a,b)['status']=='matched'


def test_unknown_source_tree_is_not_reported_as_matched(tmp_path):
    a,b=fixture(tmp_path)
    fn=getattr(module,'audit_runtime_code',None);assert callable(fn)
    result=fn(a,b,components=['not-present'])
    assert result['status']=='unavailable' and result['errors']


def test_symlinked_code_outside_tree_is_not_read_or_certified(tmp_path):
    a,b=fixture(tmp_path);outside=tmp_path/'outside.py';outside.write_text('private data\n')
    (a/'host-adapter/outside.py').symlink_to(outside)
    result=audit(a,b)
    assert result['status']=='unavailable' and result['errors']


def test_unbounded_file_is_not_read_as_a_normal_module(tmp_path):
    a,b=fixture(tmp_path)
    with (a/'host-adapter/large.py').open('wb') as stream:stream.truncate(8*1024*1024+1)
    assert audit(a,b)['status']=='unavailable'


def test_component_cannot_escape_selected_source(tmp_path):
    a,b=fixture(tmp_path);fn=getattr(module,'audit_runtime_code',None);assert callable(fn)
    assert fn(a,b,components=['../outside'])['status']=='unavailable'


def test_failed_directory_enumeration_cannot_certify_partial_tree(tmp_path,monkeypatch):
    a,b=fixture(tmp_path);walk=module.os.walk
    def enumeration_failure(folder,**kwargs):
        if kwargs.get('onerror'):kwargs['onerror'](PermissionError('unreadable private path'))
        yield from walk(folder,**kwargs)
    monkeypatch.setattr(module.os,'walk',enumeration_failure)
    result=audit(a,b)
    assert result['status']=='unavailable'
    assert 'private path' not in str(result)


def test_fifo_python_file_is_not_opened_or_treated_as_module(tmp_path,monkeypatch):
    a,b=fixture(tmp_path);fifo=b/'host-adapter/channel.py';os.mkfifo(fifo)
    original=Path.open
    def guarded_open(path,*args,**kwargs):
        if path==fifo:raise AssertionError('The auditor attempted a blocking FIFO read')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',guarded_open)
    assert audit(a,b)['status']=='unavailable'


def test_comparing_runtime_to_itself_is_not_an_independent_parity_proof(tmp_path):
    a,b=fixture(tmp_path)
    assert audit(b,b)['status']=='unavailable'
