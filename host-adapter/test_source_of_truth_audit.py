from source_of_truth_audit import audit
import source_of_truth_audit as module
from unittest.mock import patch
import json
import os
from pathlib import Path
import pytest


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


def isolated_state(tmp_path, runtime_version):
    source=tmp_path/'source';home=tmp_path/'home';state=home/'.evolving-profile'
    (source/'config').mkdir(parents=True);(state/'config').mkdir(parents=True)
    (state/'process-memory').mkdir();(home/'.codex/sessions').mkdir(parents=True)
    (source/'config/release-manifest.json').write_text(json.dumps({'product_version':'5.1.1'}))
    (state/'config/release-manifest.json').write_text(json.dumps({'product_version':runtime_version}))
    (state/'config/runtime-settings.json').write_text('{}')
    (state/'process-memory/records.json').write_text('{"schema":"agent-process-memory.v1"}')
    with patch.object(module,'ROOT',source),patch.object(module,'HOME_ROOT',state),patch.object(Path,'home',return_value=home):
        return audit()


def test_complete_isolated_deployment_passes_real_file_audit(tmp_path):
    result = isolated_state(tmp_path,'5.1.1')
    assert result['ok'] is True
    assert all(item['ok'] for item in result['checks'])


def test_unupgraded_runtime_is_reported_as_drift_not_rewritten(tmp_path):
    result = isolated_state(tmp_path,'5.1.0')
    assert result['ok'] is False
    assert next(item for item in result['checks'] if item['name']=='release_copy_matches_product')['ok'] is False
    stored=json.loads((tmp_path/'home/.evolving-profile/config/release-manifest.json').read_text())
    assert stored['product_version']=='5.1.0'


@pytest.mark.skipif(os.environ.get('EP_TEST_LIVE_STATE_AUDIT')!='1',reason='Optional operator-local deployment audit; a new source patch is not an installed runtime upgrade')
def test_live_source_of_truth_audit_is_consistent():
    result = audit()
    assert result["schema"] == "evolving-profile.source-of-truth-audit.v1"
    assert result["ok"] is True
    assert all(item["ok"] for item in result["checks"])
