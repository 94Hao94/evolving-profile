"""Small, replaceable current-task projection; never a long-term user fact."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from lib import platform_lock as fcntl
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from lib.content import extract_task_user_request


# ``working_state`` is a bounded projection over the existing task-state,
# checkpoint and scenario lanes.  It is intentionally not a new durable
# memory bank: it expires with the task-state record and follows current
# Prompt precedence.
WORKING_STATE_FIELDS = (
    "status", "phase", "goal", "next_action", "open_loops", "blocked_by",
    "pending_decisions", "checkpoint", "deadline", "last_outcome", "feedback",
)
WORKING_STATE_LIST_FIELDS = {"open_loops", "blocked_by", "pending_decisions"}
WORKING_STATE_STRING_FIELDS = {"status", "phase", "goal", "next_action", "deadline"}
WORKING_STATE_OBJECT_FIELDS = {"checkpoint", "last_outcome", "feedback"}


def _working_state_value(value: dict | None, *, objective: str | None = None) -> dict:
    """Return a stable, JSON-safe working-state projection."""
    source = dict(value or {})
    result = {}
    for field in WORKING_STATE_FIELDS:
        if field not in source or source[field] is None:
            continue
        item = source[field]
        if field in WORKING_STATE_LIST_FIELDS:
            if not isinstance(item, (list, tuple)):
                raise ValueError(f"working_state_{field}_must_be_array")
            result[field] = [str(entry) for entry in item if str(entry).strip()]
        elif field in WORKING_STATE_STRING_FIELDS:
            result[field] = str(item).strip()
        elif field in WORKING_STATE_OBJECT_FIELDS:
            if not isinstance(item, dict):
                raise ValueError(f"working_state_{field}_must_be_object")
            result[field] = dict(item)
    if objective and not result.get("goal"):
        result["goal"] = objective
    return result


def _working_state_patch(previous: dict, patch: dict, objective: str | None = None) -> dict:
    """Merge nested and convenience fields without creating duplicate stores."""
    current = _working_state_value(previous.get("working_state"), objective=objective)
    nested = patch.get("working_state")
    if nested is not None:
        if not isinstance(nested, dict):
            raise ValueError("working_state_must_be_object")
        current.update(_working_state_value(nested))
    for field in WORKING_STATE_FIELDS:
        if field in patch:
            current.update(_working_state_value({field: patch[field]}))
    if objective:
        current["goal"] = objective
    return current


class TaskStateStore:
    def __init__(self, root: Path, max_age_seconds: int = 86400):
        self.root = Path(root)
        self.max_age_seconds = max_age_seconds

    def _key(self, session_id: str) -> str:
        return hashlib.sha256(str(session_id).encode()).hexdigest()

    def _path(self, session_id: str) -> Path:
        return self.root / f"{self._key(session_id)}.json"

    @contextmanager
    def _lock(self, session_id: str, *, exclusive: bool):
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / f"{self._key(session_id)}.lock"
        with lock_path.open("a+") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _load_unlocked(self, session_id: str) -> dict | None:
        try:
            value = json.loads(self._path(session_id).read_text(encoding="utf-8"))
            expires = float(value.get("expires_at_epoch") or 0)
            if expires:
                return None if time.time() >= expires else value
            if time.time() - float(value.get("updated_at_epoch") or 0) > self.max_age_seconds:
                return None
            return value
        except (OSError, ValueError, TypeError):
            return None

    def load(self, session_id: str) -> dict | None:
        with self._lock(session_id, exclusive=False):
            return self._load_unlocked(session_id)

    def _write_unlocked(self, session_id: str, value: dict) -> dict:
        target = self._path(session_id)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.root,
                prefix=target.name + ".", suffix=".tmp", delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, target)
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return value
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _fresh_metadata(self, previous: dict | None, update_reason: str) -> dict:
        now = time.time()
        expires = now + self.max_age_seconds
        return {
            "schema": "evolving-profile.task-state.v2",
            "version": int((previous or {}).get("version") or 0) + 1,
            "update_reason": str(update_reason or "unspecified")[:160],
            "updated_at_epoch": now,
            "expires_at_epoch": expires,
            "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat(),
            "authority": "working_projection_current_prompt_wins",
            "working_state_schema": "evolving-profile.working-state.v1",
        }

    def record(self, session_id: str, prompt: str, turn_id: str | None,
               hook_invocation_id: str | None, *, continuation: bool,
               update_reason: str = "prompt_ingress") -> dict:
        with self._lock(session_id, exclusive=True):
            existing = self._load_unlocked(session_id)
            current_message = " ".join(extract_task_user_request(str(prompt or "")).split())
            if not current_message:
                # A host context message is not a new mission or continuation.
                # Keep the existing task's version, identity and expiry intact.
                return existing or {}
            previous = existing if continuation else None
            if previous:
                prior_objective = extract_task_user_request(str(previous.get('current_objective') or ''))
                previous = {**previous, 'current_objective': prior_objective} if prior_objective else None
            objective = (previous or {}).get("current_objective") or current_message
            context = objective if previous and objective != current_message else None
            value = {
                **(previous or {}),
                **self._fresh_metadata(existing, update_reason),
                "session_id": session_id,
                "turn_id": turn_id,
                "hook_invocation_id": hook_invocation_id,
                "current_objective": objective,
                "current_message": current_message,
                "continuation": bool(previous and continuation),
                "continuation_context": context,
                "source": "current_prompt" if not previous else "prior_active_task",
            }
            value["working_state"] = _working_state_patch(
                previous or {}, {}, objective=objective
            )
            value["working_state"].setdefault("status", "active")
            return self._write_unlocked(session_id, value)

    def update(self, session_id: str, patch: dict, turn_id: str | None = None,
               hook_invocation_id: str | None = None, *, expected_version: int | None = None,
               update_reason: str = "agent_update") -> dict:
        with self._lock(session_id, exclusive=True):
            previous = self._load_unlocked(session_id) or {
                "schema": "evolving-profile.task-state.v2", "session_id": session_id,
            }
            current_version = int(previous.get("version") or 0)
            if expected_version is not None and int(expected_version) != current_version:
                raise ValueError(
                    f"stale_task_state_version: expected {expected_version}, current {current_version}"
                )
            allowed = (
                "current_objective", "current_message", "constraints", "completed",
                "unresolved", "objects", "source_versions",
            )
            value = {**previous, **{key: patch[key] for key in allowed if key in patch}}
            objective = str(value.get("current_objective") or "").strip() or None
            value["working_state"] = _working_state_patch(previous, patch, objective=objective)
            value.update(
                self._fresh_metadata(previous, update_reason),
                turn_id=turn_id or previous.get("turn_id"),
                hook_invocation_id=hook_invocation_id or previous.get("hook_invocation_id"),
                source="agent_explicit_task_update",
            )
            return self._write_unlocked(session_id, value)
