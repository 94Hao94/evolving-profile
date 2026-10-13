from source_of_truth_audit import audit
import source_of_truth_audit as module
from unittest.mock import patch


def test_product_patch_zero_is_equivalent_but_other_versions_are_not(tmp_path):
    def fixture(path):
        if path == module.ROOT / "config/release-manifest.json":
            return {"product_version":"5.1.0"},None
        if path == module.HOME_ROOT / "config/release-manifest.json":
            return {"product_version":runtime_version},None
        if path == module.HOME_ROOT / "process-memory/records.json":
            return {"schema":"agent-process-memory.v1"},None
        return {},None
    for runtime_version,expected in [("5.1",True),("5.1.0",True),("5.1.1",False),("5.2",False),("5.1-rc.1",False)]:
        with patch.object(module,"read_json",side_effect=fixture),patch.object(module,"parse_env",return_value={}):
            result=module.audit()
        check=next(c for c in result['checks'] if c['name']=='release_copy_matches_product')
        assert check['ok'] is expected


def test_live_source_of_truth_audit_is_consistent():
    result = audit()
    assert result["schema"] == "evolving-profile.source-of-truth-audit.v1"
    assert result["ok"] is True
    assert all(item["ok"] for item in result["checks"])
