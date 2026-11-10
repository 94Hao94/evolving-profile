"""Bounded repair planning and source-fingerprint gates.

The service deliberately separates diagnosis/preview from side effects.  HTTP
handlers and the worker may execute the returned action only after the plan is
confirmed and its source fingerprint still matches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile
import hashlib
import threading
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4


class RepairConflictError(RuntimeError):
    """A repair plan no longer describes the current source or target."""


@dataclass
class RepairPlan:
    repair_id: str
    bank_id: str
    incident_id: str
    source_id: str | None
    mode: str
    status: str
    root_cause: str
    risk: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    source_fingerprint: str | None = None
    target_version: str | None = None
    regression_plan: list[str] = field(default_factory=list)
    apply_receipt: dict[str, Any] | None = None
    model: str = "glm-5"
    prompt_version: str = "repair.v1"
    confirmed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repair_id": self.repair_id,
            "bank_id": self.bank_id,
            "incident_id": self.incident_id,
            "source_id": self.source_id,
            "mode": self.mode,
            "status": self.status,
            "root_cause": self.root_cause,
            "risk": self.risk,
            "actions": self.actions,
            "evidence": self.evidence,
            "source_fingerprint": self.source_fingerprint,
            "target_version": self.target_version,
            "regression_plan": self.regression_plan,
            "apply_receipt": self.apply_receipt,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "confirmed_at": self.confirmed_at,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RepairPlan":
        return cls(
            repair_id=str(value["repair_id"]), bank_id=str(value["bank_id"]), incident_id=str(value["incident_id"]),
            source_id=value.get("source_id"), mode=str(value["mode"]), status=str(value["status"]),
            root_cause=str(value["root_cause"]), risk=str(value["risk"]), actions=list(value.get("actions") or []),
            evidence=list(value.get("evidence") or []), source_fingerprint=value.get("source_fingerprint"),
            target_version=value.get("target_version"), regression_plan=list(value.get("regression_plan") or []),
            apply_receipt=value.get("apply_receipt"),
            model=str(value.get("model") or "glm-5"), prompt_version=str(value.get("prompt_version") or "repair.v1"),
            confirmed_at=value.get("confirmed_at"),
        )


class RepairService:
    """Create bounded repair plans; never mutates a source during diagnosis."""

    _AUTO_TASKS = {"consolidation", "graph_maintenance"}
    _lock = threading.Lock()

    @staticmethod
    def fingerprint(value: Any) -> str:
        # Operation status responses add volatile timestamps, retry counters and
        # parsed JSON fields compared with the raw DB row used during diagnosis.
        # Fingerprint the stable source identity instead of transport formatting,
        # otherwise a safe repair preview conflicts with itself before apply.
        if isinstance(value, dict):
            stable_keys = {
                "operation_id", "id", "operation_type", "task_type",
                "status", "error_message", "result_metadata", "task_payload",
            }
            normalized = {key: value[key] for key in stable_keys if key in value}
            for key in ("result_metadata", "task_payload"):
                raw = normalized.get(key)
                if isinstance(raw, str):
                    try:
                        normalized[key] = json.loads(raw)
                    except (TypeError, ValueError):
                        pass
            value = normalized
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    _LLM_ERROR_MARKERS = (
        "source_attribution",
        "schema",
        "contract",
        "quote_selector",
        "manual_review",
    )

    def diagnose(
        self,
        *,
        bank_id: str,
        incident_id: str,
        source_id: str | None,
        operation: dict[str, Any] | None = None,
        source_fingerprint: str | None = None,
        target_version: str | None = None,
    ) -> RepairPlan:
        operation = operation or {}
        error = str(operation.get("error_message") or "").lower()
        # The authoritative operation endpoint exposes the executor kind as
        # ``operation_type``; older callers and some in-memory fixtures use
        # ``task_type``.  Normalize both so a failed mental-model refresh is
        # routed to the domain repair processor instead of falling through to
        # the generic dry-run action.
        task_type = str(operation.get("task_type") or operation.get("operation_type") or "").lower()
        llm_mode = (
            any(marker in error for marker in self._LLM_ERROR_MARKERS)
            or task_type == "refresh_mental_model"
            or task_type not in self._AUTO_TASKS
        )
        effective_fingerprint = source_fingerprint or (self.fingerprint(operation) if operation else None)
        if llm_mode:
            if task_type == "refresh_mental_model" and source_id:
                actions = [{"type": "repair_refresh_mental_model", "operation_id": source_id, "max_attempts": 1}]
                root_cause = "refresh_pipeline_failed_domain_compaction_required"
            else:
                actions = [{"type": "dry_run_retain", "source_id": source_id, "max_attempts": 1}] if source_id else []
                root_cause = "schema_or_source_contract_requires_model_preview" if source_id else "source_evidence_unavailable_ai_report"
            risk = "high"
            mode = "llm"
        elif operation.get("status") == "failed" and source_id and task_type in self._AUTO_TASKS:
            actions = [{"type": "retry_operation", "operation_id": source_id, "max_attempts": 1}]
            root_cause = "bounded_retryable_operation_failure"
            risk = "low"
            mode = "auto"
        else:
            actions = []
            root_cause = "insufficient_source_or_unknown_failure"
            risk = "high"
            mode = "llm"

        return RepairPlan(
            repair_id=str(uuid4()),
            bank_id=bank_id,
            incident_id=incident_id,
            source_id=source_id,
            mode=mode,
            status="preview_ready",
            root_cause=root_cause,
            risk=risk,
            actions=actions,
            evidence=[{"operation": operation, "task_type": task_type}],
            source_fingerprint=effective_fingerprint,
            target_version=target_version,
            regression_plan=["operation_terminal", "source_fingerprint", "service_health"],
        )

    def apply(
        self,
        plan: RepairPlan,
        *,
        current_source_fingerprint: str | None,
        confirmed: bool,
        current_target_version: str | None = None,
        executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> RepairPlan:
        if not confirmed:
            raise ValueError("repair_confirmation_required")
        with self._lock:
            if plan.status != "preview_ready":
                raise ValueError(f"repair_plan_not_applicable:{plan.status}")
            if plan.source_fingerprint != current_source_fingerprint:
                plan.status = "ai_report"
                raise RepairConflictError("source_fingerprint_changed")
            if plan.target_version != current_target_version:
                plan.status = "ai_report"
                raise RepairConflictError("target_version_changed")
            if not plan.actions:
                plan.status = "ai_report"
                raise ValueError("repair_has_no_safe_action")
            if plan.mode == "llm" and executor is None:
                plan.status = "ai_report"
                plan.apply_receipt = {"status": "ai_report", "reason": "ai_report_only_no_safe_processor"}
                return plan
            plan.apply_receipt = executor(plan.actions[0]) if executor else {"status": "planned"}
            plan.confirmed_at = datetime.now(timezone.utc).isoformat()
            plan.status = "applied"
            return plan

    def cancel(self, plan: RepairPlan) -> RepairPlan:
        with self._lock:
            if plan.status in {"applied", "failed", "ai_report", "cancelled"}:
                return plan
            plan.status = "cancelled"
            plan.confirmed_at = datetime.now(timezone.utc).isoformat()
            return plan


def repair_root() -> Path:
    return Path(os.environ.get("EVOLVING_PROFILE_STATE_ROOT", str(Path.home() / ".evolving-profile"))) / "repairs"


def save_repair_plan(plan: RepairPlan) -> Path:
    root = repair_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = root / f"{plan.repair_id}.json"
    fd, tmp_name = tempfile.mkstemp(prefix=".repair-", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(plan.to_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def load_repair_plan(repair_id: str) -> RepairPlan | None:
    path = repair_root() / f"{repair_id}.json"
    try:
        return RepairPlan.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None

