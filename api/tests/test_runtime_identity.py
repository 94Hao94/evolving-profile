from evolving_profile_api.liveness import liveness_response
from evolving_profile_api.runtime_identity import get_runtime_identity, runtime_resource_attributes


def test_runtime_identity_uses_explicit_deployment_metadata(monkeypatch):
    monkeypatch.setenv("EVOLVING_PROFILE_BUILD_SHA", "abc123")
    monkeypatch.setenv("EVOLVING_PROFILE_SOURCE_ROOT", "/srv/ep")
    monkeypatch.setenv("EVOLVING_PROFILE_CONFIG_GENERATION", "cfg-17")
    monkeypatch.setenv("EVOLVING_PROFILE_INSTANCE_ID", "instance-9")

    identity = get_runtime_identity()

    assert identity["build_sha"] == "abc123"
    assert identity["source_root"] == "/srv/ep"
    assert identity["config_generation"] == "cfg-17"
    assert identity["instance_id"] == "instance-9"
    assert identity["version"]
    assert identity["started_at"]


def test_liveness_exposes_the_same_runtime_identity(monkeypatch):
    monkeypatch.setenv("EVOLVING_PROFILE_BUILD_SHA", "liveness-sha")
    monkeypatch.setenv("EVOLVING_PROFILE_CONFIG_GENERATION", "cfg-live")

    payload = liveness_response().model_dump()

    assert payload["runtime"]["build_sha"] == "liveness-sha"
    assert payload["runtime"]["config_generation"] == "cfg-live"


def test_metrics_resource_attributes_share_api_version(monkeypatch):
    monkeypatch.setenv("EVOLVING_PROFILE_BUILD_SHA", "metrics-sha")

    attrs = runtime_resource_attributes("evolving-profile-api")

    from evolving_profile_api import __version__

    assert attrs["service.version"] == __version__
    assert attrs["service.instance.id"]
    assert attrs["evolving_profile.build_sha"] == "metrics-sha"
