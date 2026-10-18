"""Unreviewed draft reuse never substitutes for downstream acceptance."""
import copy
import importlib
import json
from pathlib import Path

import pytest

from lib.scenario_episodes import validate_episode_bundle
from lib.scenario_model import fingerprint_episode_bundle
from lib.scenario_source import read_session_source
from test_memory_recovery_scenario import fixture


PARAMS = {"model": "fixture-model", "base_url": "https://fixture.invalid/v1", "api_key": "secret-checkpoint-key"}


def checkpoint_api():
    assert importlib.util.find_spec("lib.scenario_checkpoint"), "unreviewed bundle checkpoint missing"
    return importlib.import_module("lib.scenario_checkpoint")


def test_resume_after_transient_review_failure_generates_only_once(tmp_path):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    calls = []
    def generator(actual, **params):
        assert actual == source and params == PARAMS
        calls.append("generate")
        return copy.deepcopy(bundle)
    root = tmp_path / "checkpoints"
    first, handle = api.load_or_generate(source, PARAMS, root, generator)
    # A transport error in a later independent review does not invalidate a
    # successfully generated, source-linked but still unreviewed bundle.
    with pytest.raises(TimeoutError):
        raise TimeoutError("independent review unavailable")
    second, reused = api.load_or_generate(source, PARAMS, root, generator)
    assert calls == ["generate"]
    assert first == second == validate_episode_bundle(source, bundle)
    assert handle is not None and reused is not None
    contents = "\n".join(path.read_text() for path in root.rglob("*.json"))
    assert PARAMS["api_key"] not in contents
    assert PARAMS["base_url"] not in contents
    assert PARAMS["model"] not in contents
    assert "model_review_passed" not in contents


def test_semantic_invalidation_preserves_immutable_bundle_and_regenerates(tmp_path):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    calls = []
    def generator(*_args, **_params):
        calls.append(1)
        return copy.deepcopy(bundle)
    root = tmp_path / "checkpoints"
    _, handle = api.load_or_generate(source, PARAMS, root, generator)
    blobs = {p: p.read_bytes() for p in root.rglob(f"{fingerprint_episode_bundle(bundle)}.json")}
    assert len(blobs) == 1
    handle.invalidate("automated_source_coverage_incomplete")
    assert all(path.read_bytes() == original for path, original in blobs.items())
    _, renewed = api.load_or_generate(source, PARAMS, root, generator)
    assert calls == [1, 1]
    assert renewed is not None


@pytest.mark.parametrize("field", ["model", "base_url"])
def test_provider_change_cannot_reuse_prior_generated_bundle(tmp_path, field):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    calls = []
    def generator(*_args, **_params):
        calls.append(1)
        return copy.deepcopy(bundle)
    root = tmp_path / "checkpoints"
    api.load_or_generate(source, PARAMS, root, generator)
    api.load_or_generate(source, {**PARAMS, field: PARAMS[field] + "-changed"}, root, generator)
    assert calls == [1, 1]


def test_source_manifest_locator_change_cannot_reuse_even_with_same_revision(tmp_path):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    calls = []
    def generator(actual, **_params):
        calls.append(1)
        value = copy.deepcopy(bundle)
        for episode in value["episodes"]:
            episode["draft"]["source_files"] = actual["source_files"]
        return validate_episode_bundle(actual, value)
    root = tmp_path / "checkpoints"
    api.load_or_generate(source, PARAMS, root, generator)
    relocated = copy.deepcopy(source)
    prior = source["messages"][0]["source_path"]
    target = Path(prior).with_name("relocated.jsonl")
    target.write_bytes(Path(prior).read_bytes())
    relocated["source_files"] = [str(target)]
    for message in relocated["messages"]:
        message["source_path"] = str(target)
    api.load_or_generate(relocated, PARAMS, root, generator)
    assert calls == [1, 1]


def test_current_raw_role_mutation_blocks_reuse_and_generation(tmp_path):
    api = checkpoint_api()
    _, path, source, bundle, _ = fixture(tmp_path)
    calls = []
    def generator(*_args, **_params):
        calls.append(1)
        return copy.deepcopy(bundle)
    root = tmp_path / "checkpoints"
    api.load_or_generate(source, PARAMS, root, generator)
    raw = path.read_text()
    assert '"role": "user"' in raw
    path.write_text(raw.replace('"role": "user"', '"role": "assistant"', 1))
    with pytest.raises(ValueError, match="scenario_checkpoint_source_changed"):
        api.load_or_generate(source, PARAMS, root, generator)
    assert calls == [1]


def test_protected_source_never_calls_generator_or_creates_cache(tmp_path):
    api = checkpoint_api()
    session_root, _, source, _, _ = fixture(tmp_path, prefix="不要修改任何记忆。")
    source = read_session_source(source["thread_id"], session_root, max_chars=60000)
    def forbidden(*_args, **_params):
        raise AssertionError("protected source reached generation")
    root = tmp_path / "checkpoints"
    with pytest.raises(ValueError, match="scenario_knowledge_write_prohibited"):
        api.load_or_generate(source, PARAMS, root, forbidden)
    assert not root.exists()


@pytest.mark.parametrize("corruption", ["index_json", "missing_blob", "invalid_bundle", "mismatched_binding", "oversized_index"])
def test_corrupt_or_invalid_checkpoint_never_bypasses_validation(tmp_path, corruption):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    calls = []
    def generator(*_args, **_params):
        calls.append(1)
        return copy.deepcopy(bundle)
    root = tmp_path / "checkpoints"
    api.load_or_generate(source, PARAMS, root, generator)
    index = next(root.rglob("index.json"))
    if corruption == "index_json":
        index.write_text("{")
    elif corruption == "missing_blob":
        next(root.rglob(f"{fingerprint_episode_bundle(bundle)}.json")).unlink()
    elif corruption == "mismatched_binding":
        value = json.loads(index.read_text())
        value["provider_sha256"] = "0" * 64
        index.write_text(json.dumps(value))
    elif corruption == "oversized_index":
        index.write_text(" " * 5000)
    else:
        value = json.loads(index.read_text())
        invalid = copy.deepcopy(bundle)
        invalid["episodes"][0]["draft"]["state"]["goal"]["message_ids"] = [source["messages"][1]["evidence_id"]]
        digest = fingerprint_episode_bundle(invalid)
        index.with_name(f"{digest}.json").write_text(json.dumps(invalid))
        value["bundle_sha256"] = digest
        index.write_text(json.dumps(value))
    actual, _ = api.load_or_generate(source, PARAMS, root, generator)
    assert calls == [1, 1]
    assert actual == validate_episode_bundle(source, bundle)


def test_invalid_fresh_bundle_is_not_saved(tmp_path):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    invalid = copy.deepcopy(bundle)
    invalid["parent_source_revision"] = "stale"
    root = tmp_path / "checkpoints"
    with pytest.raises(ValueError, match="scenario_episode_bundle_stale_or_invalid"):
        api.load_or_generate(source, PARAMS, root, lambda *_args, **_params: invalid)
    assert not list(root.rglob("*.json"))


def test_source_change_cannot_reuse_stale_bundle_or_save_invalid_regeneration(tmp_path):
    api = checkpoint_api()
    session_root, path, source, bundle, _ = fixture(tmp_path)
    calls = []
    def generator(*_args, **_params):
        calls.append(1)
        return copy.deepcopy(bundle)
    root = tmp_path / "checkpoints"
    api.load_or_generate(source, PARAMS, root, generator)
    path.write_text(path.read_text().replace("请编制项目甲方案", "请编制新的项目方案"))
    changed = read_session_source(source["thread_id"], session_root, max_chars=60000)
    with pytest.raises(ValueError, match="scenario_episode_bundle_stale_or_invalid"):
        api.load_or_generate(changed, PARAMS, root, generator)
    assert calls == [1, 1]
    assert len(list(root.rglob("index.json"))) == 1


def test_fresh_prohibition_blocks_cached_bundle_without_checkpoint_writes(tmp_path):
    api = checkpoint_api()
    session_root, path, source, bundle, _ = fixture(tmp_path)
    root = tmp_path / "checkpoints"
    api.load_or_generate(source, PARAMS, root, lambda *_args, **_params: bundle)
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    path.write_text(path.read_text().replace("请编制项目甲方案", "不要修改任何记忆。只改写一句话。"))
    protected = read_session_source(source["thread_id"], session_root, max_chars=60000)
    def forbidden(*_args, **_params):
        raise AssertionError("fresh prohibition reached generation")
    with pytest.raises(ValueError, match="scenario_knowledge_write_prohibited"):
        api.load_or_generate(protected, PARAMS, root, forbidden)
    assert {p: p.read_bytes() for p in root.rglob("*.json")} == before


def test_corrupted_immutable_blob_is_not_overwritten_or_accepted(tmp_path):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    root = tmp_path / "checkpoints"
    api.load_or_generate(source, PARAMS, root, lambda *_args, **_params: bundle)
    blob = next(root.rglob(f"{fingerprint_episode_bundle(bundle)}.json"))
    blob.write_text("{")
    calls = []
    def generator(*_args, **_params):
        calls.append(1)
        return bundle
    actual, handle = api.load_or_generate(source, PARAMS, root, generator)
    assert actual == validate_episode_bundle(source, bundle)
    assert handle is None
    assert calls == [1]
    assert blob.read_text() == "{"


def test_symlink_root_disables_cache_without_target_writes(tmp_path):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    target = tmp_path / "outside"
    target.mkdir()
    root = tmp_path / "checkpoints"
    root.symlink_to(target, target_is_directory=True)
    calls = []
    def generator(*_args, **_params):
        calls.append(1)
        return bundle
    actual, handle = api.load_or_generate(source, PARAMS, root, generator)
    assert actual == bundle and handle is None
    assert calls == [1]
    assert list(target.iterdir()) == []


def test_api_key_rotation_keeps_provider_binding_and_errors_do_not_persist_secrets(tmp_path):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    root = tmp_path / "checkpoints"
    _, handle = api.load_or_generate(source, PARAMS, root, lambda *_args, **_params: bundle)
    def forbidden(*_args, **_params):
        raise AssertionError("API key rotation regenerated an unchanged provider bundle")
    actual, _ = api.load_or_generate(source, {**PARAMS, "api_key": "rotated-key"}, root, forbidden)
    assert actual == bundle
    handle.invalidate(ValueError("provider rejected " + PARAMS["api_key"]))
    assert PARAMS["api_key"] not in "\n".join(p.read_text() for p in root.rglob("*.json"))


def test_checkpoint_write_denied_does_not_reject_valid_fresh_generation(tmp_path, monkeypatch):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    def denied(*_args, **_kwargs):
        raise PermissionError("fixture filesystem write denied")
    monkeypatch.setattr(api.os, "link", denied)
    actual, handle = api.load_or_generate(source, PARAMS, tmp_path / "checkpoints",
                                          lambda *_args, **_params: bundle)
    assert actual == bundle and handle is None


def test_cache_raw_line_budget_disables_reuse_without_reclassifying_source(tmp_path, monkeypatch):
    api = checkpoint_api()
    _, _, source, bundle, _ = fixture(tmp_path)
    monkeypatch.setattr(api, "MAX_CHECKPOINT_BYTES", 64)
    root = tmp_path / "checkpoints"
    calls = []
    def generator(*_args, **_params):
        calls.append(1)
        return bundle
    actual, handle = api.load_or_generate(source, PARAMS, root, generator)
    assert actual == bundle and handle is None
    assert calls == [1]
    assert not root.exists()
