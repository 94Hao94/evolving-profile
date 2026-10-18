"""An explicit selected-state projection is not an implicit global installation edit."""
import importlib.util,json,hashlib
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
def module():
    spec=importlib.util.spec_from_file_location('project_metadata',ROOT/'scripts/project-release-metadata.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
def package(tmp_path):
    root=tmp_path/'package';(root/'config').mkdir(parents=True)
    (root/'VERSION').write_text('5.1.2\n')
    (root/'config/release-manifest.json').write_text(json.dumps({'product_version':'5.1.2','release_channel':'candidate','build_id':'fixture'}))
    return root
def test_preview_creates_no_state_and_apply_records_selected_version(tmp_path):
    root=package(tmp_path);state=tmp_path/'selected'
    m=module();report=m.project(root,state)
    assert report['before_sha256'] is None and not state.exists()
    result=m.project(root,state,apply=True,expected='absent')
    assert result['status']=='applied'
    assert json.loads((state/'config/release-manifest.json').read_text())['product_version']=='5.1.2'
def test_stale_expected_revision_preserves_operator_metadata(tmp_path):
    root=package(tmp_path);state=tmp_path/'selected';target=state/'config/release-manifest.json'
    target.parent.mkdir(parents=True);target.write_text('{"product_version":"old"}')
    before=target.read_bytes()
    with pytest.raises(ValueError,match='revision_conflict'):module().project(root,state,apply=True,expected='absent')
    assert target.read_bytes()==before
def test_source_version_mismatch_does_not_write(tmp_path):
    root=package(tmp_path);(root/'VERSION').write_text('5.1.3\n');state=tmp_path/'selected'
    with pytest.raises(ValueError,match='release_manifest_version_mismatch'):module().project(root,state,apply=True,expected='absent')
    assert not state.exists()
def test_explicit_upgrade_keeps_backup_of_previous_projection(tmp_path):
    root=package(tmp_path);state=tmp_path/'selected';target=state/'config/release-manifest.json'
    target.parent.mkdir(parents=True);target.write_bytes(b'{"product_version":"older"}\n');before=target.read_bytes()
    result=module().project(root,state,apply=True,expected=hashlib.sha256(before).hexdigest())
    assert Path(result['backup']).read_bytes()==before
