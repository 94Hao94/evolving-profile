"""Optional disk reuse of an unreviewed, source-linked episode bundle only.

Every caller must still run independent episode review, whole-source coverage
review, and publication validation. No acceptance receipt is cached here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .scenario_episodes import validate_episode_bundle
from .scenario_model import fingerprint_episode_bundle
from .scenario_source import revision_for_messages


MAX_CHECKPOINT_BYTES = 4 * 1024 * 1024
_SCHEMA = "scenario-unreviewed-bundle-checkpoint.v1"


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _qualify_source(source):
    from .context_incremental import qualify_summary_input
    qualification = qualify_summary_input(source)
    if qualification["status"] != "eligible":
        raise ValueError(qualification["reason"] or "scenario_source_incomplete")
    if revision_for_messages(source["messages"], source.get("context_metadata_exclusions")) != source.get("source_revision"):
        raise ValueError("scenario_checkpoint_source_changed")
    # Verify the exact currently readable raw roles and locators, rather than
    # accepting an old in-memory source object as evidence of an unchanged file.
    rows = [*source["messages"], *(source.get("context_metadata_exclusions") or [])]
    try:
        for row in rows:
            path, offset = Path(row["source_path"]), row["byte_offset"]
            if (str(path) not in source["source_files"] or type(offset) is not int
                    or offset < 0 or path.is_symlink()):
                raise ValueError("scenario_checkpoint_source_changed")
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as stream:
                stream.seek(offset)
                raw = stream.readline(MAX_CHECKPOINT_BYTES + 1)
            if len(raw) > MAX_CHECKPOINT_BYTES:
                # This bound belongs only to the optional cache verifier.
                # The ordinary independent review/publisher still applies.
                return False
            payload = json.loads(raw).get("payload") or {}
            if (hashlib.sha256(raw).hexdigest() != row["raw_line_sha256"]
                    or payload.get("role") != row.get("role", row.get("original_role"))):
                raise ValueError("scenario_checkpoint_source_changed")
    except (OSError, KeyError, TypeError, AttributeError, ValueError):
        raise ValueError("scenario_checkpoint_source_changed") from None
    return True


def _read_json(path, limit=MAX_CHECKPOINT_BYTES):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None


def _directory(root, parts):
    path = Path(root).expanduser()
    if path.is_symlink():
        raise ValueError("scenario_checkpoint_path_invalid")
    path.mkdir(parents=True, exist_ok=True)
    path = path.resolve()
    for part in parts:
        path = path / part  # Every component is a locally computed SHA-256.
        if path.is_symlink():
            raise ValueError("scenario_checkpoint_path_invalid")
        path.mkdir(exist_ok=True)
    return path


def _atomic_json(path, value, *, immutable=False):
    raw = _bytes(value)
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise ValueError("scenario_checkpoint_bundle_too_large")
    fd, temporary = tempfile.mkstemp(prefix=".checkpoint-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            try:
                os.link(temporary, path)
            except FileExistsError:
                existing = _read_json(path)
                if existing != value:
                    raise ValueError("scenario_checkpoint_blob_conflict") from None
        else:
            os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


class ScenarioCheckpoint:
    """Handle to draft reuse eligibility; never a review/publication grant."""

    def __init__(self, directory, source_sha, provider_sha):
        self.directory = directory
        self.binding = {"schema": _SCHEMA, "source_manifest_sha256": source_sha,
                        "provider_sha256": provider_sha}

    def _load(self, source):
        state = _read_json(self.directory / "index.json", 4096)
        if (not state or any(state.get(key) != value for key, value in self.binding.items())
                or state.get("status") != "reusable_unreviewed_bundle"):
            return None
        digest = state.get("bundle_sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return None
        bundle = _read_json(self.directory / (digest + ".json"))
        if bundle is None or fingerprint_episode_bundle(bundle) != digest:
            return None
        try:
            return validate_episode_bundle(source, bundle)
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, RecursionError):
            return None

    def _save(self, bundle):
        digest = fingerprint_episode_bundle(bundle)
        _atomic_json(self.directory / (digest + ".json"), bundle, immutable=True)
        _atomic_json(self.directory / "index.json", {**self.binding,
                     "status": "reusable_unreviewed_bundle", "bundle_sha256": digest})

    def invalidate(self, reason):
        state = _read_json(self.directory / "index.json", 4096)
        if not state or any(state.get(key) != value for key, value in self.binding.items()):
            return
        # Raw provider exceptions can contain credentials or source text. Keep
        # only bounded internal error codes; never persist the exception body.
        code = str(reason)
        if not re.fullmatch(r"(?:scenario|automated)_[a-z_]{1,100}", code):
            code = "scenario_downstream_validation_rejected"
        try:
            _atomic_json(self.directory / "index.json", {**self.binding,
                         "bundle_sha256": state.get("bundle_sha256"), "status": "invalidated", "reason": code})
        except (OSError, ValueError):
            pass  # Cache failure must not replace the original review error.


def load_or_generate(source, params, checkpoint_root, generator):
    """Return (validated bundle, optional invalidation handle).

    The generator receives ``(source, **params)``. Credentials are passed only
    to it; provider binding stores a digest of model/base URL, never params.
    """
    cache_available = _qualify_source(source)  # Before generation, reuse, or any cache write.
    source_sha = _digest(source)
    checkpoint = None
    if checkpoint_root is not None and cache_available:
        provider_sha = _digest({key: params.get(key) for key in ("model", "base_url")})
        try:
            directory = _directory(checkpoint_root, (_digest(source["thread_id"]), source_sha, provider_sha))
            checkpoint = ScenarioCheckpoint(directory, source_sha, provider_sha)
            bundle = checkpoint._load(source)
            if bundle is not None:
                return bundle, checkpoint
        except (OSError, ValueError):
            checkpoint = None
    bundle = validate_episode_bundle(source, generator(source, **params))
    if not _qualify_source(source):
        checkpoint = None
    if _digest(source) != source_sha:
        raise ValueError("scenario_checkpoint_source_changed")
    if checkpoint is not None:
        try:
            checkpoint._save(bundle)
        except (OSError, ValueError):
            checkpoint = None  # Valid fresh generation still needs all reviews.
    return bundle, checkpoint
