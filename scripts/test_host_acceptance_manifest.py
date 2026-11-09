import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host-adapter'))


def test_mac_fixture_never_satisfies_windows_actual_execution():
    from lib.host_integration.acceptance import build_acceptance_manifest
    out=build_acceptance_manifest([{'status':'passed','platform':'windows','evidence_kind':'fixture','provider_calls':0}],{'profiles':[]})
    assert out['windows_execution']=='not_run'
    assert out['real_host_verified'] is False


def test_missing_receipts_remain_unknown_and_negative_tests_required():
    from lib.host_integration.acceptance import build_acceptance_manifest
    out=build_acceptance_manifest([],{'profiles':[]})
    assert out['status']=='not_run' and out['provider_calls'] is None
    assert 'disabled_tool_denied_stdio' in out['missing_checks']
    assert 'disabled_tool_denied_http' in out['missing_checks']


def test_nonzero_provider_calls_fail_preparation_budget():
    from lib.host_integration.acceptance import build_acceptance_manifest
    out=build_acceptance_manifest([{'status':'passed','provider_calls':1}],{'profiles':[]})
    assert out['status']=='budget_violation'


def test_unknown_dependency_is_explicit_and_matrix_is_registry_owned():
    from lib.host_integration.acceptance import build_acceptance_manifest,render_matrix
    registry={'sha256':'r','profiles':[{'id':'future_host','labels':{'en':'Future host','zh-CN':'未来宿主'},'documented':{'mcp_stdio':True}}]}
    out=build_acceptance_manifest([{'status':'blocked','provider_calls':0,'error_code':'dependency_unavailable'}],registry)
    assert out['status']=='blocked'
    matrix=render_matrix(registry,'zh-CN')
    assert '未来宿主' in matrix and 'r' in matrix
