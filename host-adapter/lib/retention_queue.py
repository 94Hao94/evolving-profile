"""Persistent token-aware retention queue for Codex hooks."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


DEFAULT_STATE_PATH = Path.home() / ".evolving-profile/codex/state/retention-queue.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value) -> datetime:
    if value is None:
        return _utcnow()
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def estimate_tokens(text: str) -> int:
    """Conservative local estimate for mixed Chinese/English transcripts."""
    value = str(text or "")
    cjk = len(re.findall(r"[\u3400-\u9fff]", value))
    ascii_chars = len(re.findall(r"[A-Za-z0-9]", value))
    other = max(0, len(re.sub(r"\s", "", value)) - cjk - ascii_chars)
    return max(1, cjk + math.ceil(ascii_chars / 4) + math.ceil(other / 2))


def split_content(text: str, max_tokens: int) -> list[str]:
    """Split text in order so every persisted queue item stays under the hard cap."""
    remaining = str(text or "").strip()
    limit = max(1, int(max_tokens))
    parts = []
    while remaining and estimate_tokens(remaining) > limit:
        low, high = 1, len(remaining)
        while low < high:
            middle = (low + high + 1) // 2
            if estimate_tokens(remaining[:middle]) <= limit:
                low = middle
            else:
                high = middle - 1
        cut = max(1, low)
        boundary_floor = max(1, int(cut * 0.75))
        newline = remaining.rfind("\n", boundary_floor, cut)
        space = remaining.rfind(" ", boundary_floor, cut)
        boundary = max(newline, space)
        if boundary >= boundary_floor:
            cut = boundary + 1
        part = remaining[:cut].strip()
        if not part:
            part = remaining[:cut]
        parts.append(part)
        remaining = remaining[cut:].strip()
    if remaining:
        parts.append(remaining)
    return parts


class RetentionQueue:
    def __init__(self, path=DEFAULT_STATE_PATH, threshold_tokens: int = 12_000):
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self.threshold_tokens = max(1, int(threshold_tokens))

    def _empty(self):
        return {"version": 1, "sessions": {}, "items": []}

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = open(self.lock_path, "a+", encoding="utf-8")
        if fcntl is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = self._empty()
        if not isinstance(data, dict):
            data = self._empty()
        data.setdefault("version", 1)
        data.setdefault("sessions", {})
        data.setdefault("items", [])
        return data

    def _write(self, data):
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)

    @staticmethod
    def _project_id(bank_id: str, project: str) -> str:
        return f"{bank_id}::{project}"

    def session_cursor(self, session_id: str, bank_id: str, project: str) -> int:
        key = f"{self._project_id(bank_id, project)}::{session_id}"
        with self._locked():
            return int(self._read()["sessions"].get(key, 0))

    def discard_project(self, project: str) -> int:
        """Remove queued probe content for one exact project path.

        This is intentionally exact-match only.  It is used by an isolated
        E2E canary to exercise the real read/injection path without later
        retaining its synthetic prompts into a user's production Bank.
        """
        project = str(project or "")
        if not project:
            return 0
        with self._locked():
            state = self._read()
            before = len(state["items"])
            state["items"] = [item for item in state["items"] if str(item.get("project") or "") != project]
            for key in list(state["sessions"]):
                if key.split("::", 2)[1:2] == [project]:
                    state["sessions"].pop(key, None)
            removed = before - len(state["items"])
            if removed:
                self._write(state)
            return removed

    def capture(
        self,
        session_id: str,
        message_count: int,
        bank_id: str,
        project: str,
        content: str,
        metadata: dict,
        captured_at=None,
    ) -> bool:
        project = str(project or "unknown")
        project_id = self._project_id(bank_id, project)
        session_key = f"{project_id}::{session_id}"
        captured = _as_utc(captured_at)
        content = str(content or "").strip()
        with self._locked():
            state = self._read()
            previous_count = int(state["sessions"].get(session_key, 0))
            if int(message_count) <= previous_count:
                return False
            state["sessions"][session_key] = int(message_count)
            if content:
                parts = split_content(content, self.threshold_tokens)
                for part_index, part in enumerate(parts, start=1):
                    item_id = hashlib.sha256(
                        f"{session_key}\0{message_count}\0{part_index}\0{part}".encode("utf-8")
                    ).hexdigest()
                    if any(item.get("id") == item_id for item in state["items"]):
                        continue
                    item_metadata = {str(k): str(v) for k, v in (metadata or {}).items()}
                    if len(parts) > 1:
                        item_metadata["queue_part"] = f"{part_index}/{len(parts)}"
                    state["items"].append(
                        {
                            "id": item_id,
                            "session_id": session_id,
                            "message_count": int(message_count),
                            "bank_id": bank_id,
                            "project": project,
                            "project_id": project_id,
                            "content": part,
                            "estimated_tokens": estimate_tokens(part),
                            "metadata": item_metadata,
                            "captured_at": captured.isoformat().replace("+00:00", "Z"),
                        }
                    )
            self._write(state)
            return bool(content)

    def _select_batches(self, state, force_tail=False, min_age_seconds=0):
        now = _utcnow()
        groups = {}
        for item in state["items"]:
            if item.get("operation_id") or item.get('retention_origin_hold'):
                continue
            groups.setdefault(item["project_id"], []).append(item)

        batches = []
        for project_id, items in sorted(groups.items()):
            def item_order(row):
                part = str((row.get("metadata") or {}).get("queue_part", "1/1"))
                try:
                    part_index = int(part.split("/", 1)[0])
                except (TypeError, ValueError):
                    part_index = 1
                return (
                    row.get("captured_at", ""),
                    row.get("session_id", ""),
                    int(row.get("message_count", 0)),
                    part_index,
                    row["id"],
                )

            items.sort(key=item_order)
            total = sum(int(item.get("estimated_tokens", 0)) for item in items)
            oldest = min(_as_utc(item.get("captured_at")) for item in items)
            old_enough = (now - oldest).total_seconds() >= max(0, int(min_age_seconds))
            if total < self.threshold_tokens and not (force_tail and old_enough):
                continue

            remaining = list(items)
            while remaining:
                remaining_tokens = sum(int(item.get("estimated_tokens", 0)) for item in remaining)
                if not force_tail and remaining_tokens < self.threshold_tokens:
                    break
                selected = []
                selected_tokens = 0
                for item in remaining:
                    item_tokens = int(item.get("estimated_tokens", 0))
                    if selected and selected_tokens + item_tokens > self.threshold_tokens:
                        break
                    selected.append(item)
                    selected_tokens += item_tokens
                    if selected_tokens >= self.threshold_tokens:
                        break
                if not selected:
                    break
                digest = hashlib.sha256(
                    "\n".join(item["id"] for item in selected).encode("ascii")
                ).hexdigest()[:24]
                bank_id = selected[0]["bank_id"]
                project = selected[0]["project"]
                session_ids = sorted({item["session_id"] for item in selected})
                content = "\n\n".join(
                    f"[pending item {index + 1}/{len(selected)}; session={item['session_id']}]\n{item['content']}"
                    for index, item in enumerate(selected)
                )
                batches.append(
                    {
                        "batch_id": digest,
                        "item_ids": [item["id"] for item in selected],
                        "bank_id": bank_id,
                        "project": project,
                        "project_id": project_id,
                        "session_ids": session_ids,
                        "estimated_tokens": selected_tokens,
                        "content": content,
                        "oldest_at": oldest.isoformat().replace("+00:00", "Z"),
                        "priority_tail": any(
                            str((item.get("metadata") or {}).get("priority_tail", "")).lower()
                            == "true"
                            for item in selected
                        ),
                    }
                )
                remaining = remaining[len(selected):]
        return batches

    def ready_batches(self, force_tail=False, min_age_seconds=0, config=None):
        if config is None:
            from .config import load_config
            config=load_config()
        from .retention_policy import retention_exclusion
        with self._locked():
            state=self._read();changed=False
            for item in state['items']:
                if item.get('operation_id'):continue
                if item.get('session_id') in config.get('diagnosticSessionIds',[]):
                    if (item.get('metadata') or {}).get('prompt_origin')!='test_probe':
                        item.setdefault('metadata',{})['prompt_origin']='test_probe';changed=True
                reason=('recorded_diagnostic_origin' if (item.get('metadata') or {}).get('prompt_origin')=='test_probe' else
                        retention_exclusion(item.get('project'),[item.get('session_id')],config))
                if item.get('retention_origin_hold','')!=reason:
                    item['retention_origin_hold']=reason;changed=True
            if changed:self._write(state)
            # Exclude individual items before grouping. Dropping a mixed batch
            # afterwards would also strand genuine user input in that project.
            return self._select_batches(state, force_tail, min_age_seconds)

    def mark_submitted(self, batch_id: str, operation_id: str) -> bool:
        with self._locked():
            state = self._read()
            candidates = self._select_batches(state, force_tail=True, min_age_seconds=0)
            batch = next((row for row in candidates if row["batch_id"] == batch_id), None)
            if batch is None:
                return False
            item_ids = set(batch["item_ids"])
            submitted_at = _utcnow().isoformat().replace("+00:00", "Z")
            for item in state["items"]:
                if item["id"] in item_ids:
                    item["batch_id"] = batch_id
                    item["operation_id"] = operation_id
                    item["submitted_at"] = submitted_at
            self._write(state)
            return True

    def pending_operations(self):
        with self._locked():
            state = self._read()
            return sorted({item["operation_id"] for item in state["items"] if item.get("operation_id")})

    def reconcile(self, statuses: dict):
        completed = {op for op, status in statuses.items() if status == "completed"}
        retryable = {op for op, status in statuses.items() if status in {"failed", "cancelled", "not_found"}}
        with self._locked():
            state = self._read()
            kept = []
            for item in state["items"]:
                operation_id = item.get("operation_id")
                if operation_id in completed:
                    continue
                if operation_id in retryable:
                    item.pop("operation_id", None)
                    item.pop("batch_id", None)
                    item.pop("submitted_at", None)
                kept.append(item)
            state["items"] = kept
            self._write(state)

    def migrate_bank(self, old_bank_id: str, new_bank_id: str, requeue_submitted: bool = False):
        """Atomically move queued work and cursors to another bank."""
        if not old_bank_id or not new_bank_id or old_bank_id == new_bank_id:
            return {"migrated_items": 0, "migrated_cursors": 0, "split_items": 0, "requeued": 0}
        report = {"migrated_items": 0, "migrated_cursors": 0, "split_items": 0, "requeued": 0}
        with self._locked():
            state = self._read()
            old_prefix = f"{old_bank_id}::"
            for key, cursor in list(state["sessions"].items()):
                if not key.startswith(old_prefix):
                    continue
                new_key = f"{new_bank_id}::{key[len(old_prefix):]}"
                state["sessions"][new_key] = max(int(cursor), int(state["sessions"].get(new_key, 0)))
                del state["sessions"][key]
                report["migrated_cursors"] += 1

            migrated = []
            for item in state["items"]:
                if item.get("bank_id") != old_bank_id:
                    migrated.append(item)
                    continue
                report["migrated_items"] += 1
                parts = split_content(item.get("content", ""), self.threshold_tokens)
                report["split_items"] += max(0, len(parts) - 1)
                for part_index, part in enumerate(parts, start=1):
                    replacement = dict(item)
                    replacement["id"] = hashlib.sha256(
                        f"{item['id']}\0{new_bank_id}\0{part_index}\0{part}".encode("utf-8")
                    ).hexdigest()
                    replacement["bank_id"] = new_bank_id
                    replacement["project_id"] = self._project_id(new_bank_id, item["project"])
                    replacement["content"] = part
                    replacement["estimated_tokens"] = estimate_tokens(part)
                    metadata = dict(item.get("metadata") or {})
                    if len(parts) > 1:
                        metadata["queue_part"] = f"{part_index}/{len(parts)}"
                    replacement["metadata"] = metadata
                    if requeue_submitted and replacement.get("operation_id"):
                        replacement.pop("operation_id", None)
                        replacement.pop("batch_id", None)
                        replacement.pop("submitted_at", None)
                        report["requeued"] += 1
                    migrated.append(replacement)
            state["items"] = migrated
            self._write(state)
        return report

    def snapshot(self):
        with self._locked():
            state = self._read()
        projects = {}
        for item in state["items"]:
            project = projects.setdefault(
                item["project_id"],
                {"bank_id": item["bank_id"], "project": item["project"], "items": 0, "estimated_tokens": 0},
            )
            project["items"] += 1
            project["estimated_tokens"] += int(item.get("estimated_tokens", 0))
        return {**state, "projects": projects}
