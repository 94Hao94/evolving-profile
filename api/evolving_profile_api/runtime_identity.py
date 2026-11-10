"""Stable runtime identity shared by API, worker, controller bridges, and telemetry."""

from __future__ import annotations

import hashlib
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_INSTANCE_ID = os.getenv("EVOLVING_PROFILE_INSTANCE_ID") or f"{socket.gethostname()}-{uuid.uuid4()}"
_STARTED_AT = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _source_build_sha() -> str:
    """Derive a local source fingerprint when a release injects no build SHA."""
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    try:
        for path in sorted(root.rglob("*.py")):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    except OSError:
        return "unknown"
    return f"source-{digest.hexdigest()[:16]}"


def _version() -> str:
    from evolving_profile_api import __version__

    return __version__


def get_runtime_identity() -> dict[str, str]:
    """Return deployment metadata with deterministic fallbacks.

    Environment variables are deliberately optional so local development keeps
    working. Operators can inject a release SHA, source root, configuration
    generation, and instance id without rebuilding the package.
    """

    source_root = os.getenv("EVOLVING_PROFILE_SOURCE_ROOT")
    if not source_root:
        source_root = str(Path(__file__).resolve().parents[1])
    return {
        "version": _version(),
        "build_sha": os.getenv("EVOLVING_PROFILE_BUILD_SHA") or _source_build_sha(),
        "source_root": source_root,
        "config_generation": os.getenv("EVOLVING_PROFILE_CONFIG_GENERATION", "unknown"),
        "instance_id": os.getenv("EVOLVING_PROFILE_INSTANCE_ID", _INSTANCE_ID),
        "started_at": _STARTED_AT,
    }


def runtime_resource_attributes(service_name: str) -> dict[str, Any]:
    """Return OpenTelemetry resource attributes for a service instance."""

    identity = get_runtime_identity()
    return {
        "service.name": service_name,
        "service.version": identity["version"],
        "service.instance.id": identity["instance_id"],
        "evolving_profile.build_sha": identity["build_sha"],
        "evolving_profile.source_root": identity["source_root"],
        "evolving_profile.config_generation": identity["config_generation"],
        "evolving_profile.started_at": identity["started_at"],
    }
