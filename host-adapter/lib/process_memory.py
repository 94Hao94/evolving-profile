"""EP5.0 Agent Process Memory contract and local state store.

The store is deliberately independent from Bank facts. It keeps raw execution
evidence, derived process records, and task-local capability observations in a
small versioned JSON document so the first EP5.0 rollout can be audited and
rolled back without a database migration.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "agent-process-memory.v1"
TAXONOMY_VERSION = "task-archetype.v1"
DIMENSION_REGISTRY_VERSION = "process-dimensions.v1"
KINDS = {"trace", "event", "process_observation", "episode", "pattern", "skill", "process_draft", "capability_observation"}
PHASES = {"understand", "plan", "retrieve", "act", "observe", "verify", "recover", "deliver", "reflect"}
MATURITIES = {"observed", "diagnosed", "repaired", "verified", "replicated", "generalized", "deprecated"}
OUTCOMES = {"correct", "partially_correct", "recovered", "regressed", "blocked", "ambiguous", "inefficient", "not_applicable"}
INTERVENTIONS = {"observe", "hint", "recommend", "scaffold", "guard"}
TRANSFER = {"unknown", "candidate", "verified", "blocked"}
INDEPENDENT_VERIFIERS = {
    "deterministic_tool", "automated_test", "render_or_visual_check", "source_check",
    "user_acceptance", "episode_replication", "pattern_replication",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"pm_{prefix}_{uuid.uuid4().hex}"


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("process_memory_record_invalid")
    value = dict(record)
    kind = str(value.get("kind") or "").strip()
    if kind not in KINDS:
        raise ValueError("process_memory_kind_invalid")
    phase = str(value.get("phase") or "observe").strip()
    if phase not in PHASES:
        raise ValueError("process_memory_phase_invalid")
    maturity = str(value.get("maturity") or ("observed" if kind in {"trace", "event", "process_observation", "capability_observation"} else "candidate"))
    if maturity not in MATURITIES and maturity != "candidate":
        raise ValueError("process_memory_maturity_invalid")
    outcome = str(value.get("outcome") or "ambiguous")
    if outcome not in OUTCOMES and kind != "capability_observation":
        raise ValueError("process_memory_outcome_invalid")
    source_trace_ids = [str(item) for item in _list(value.get("source_trace_ids")) if str(item)]
    if kind != "capability_observation" and not source_trace_ids:
        raise ValueError("process_memory_source_trace_required")
    verification = _list(value.get("verification_evidence"))
    value.update({
        "schema_version": str(value.get("schema_version") or SCHEMA_VERSION),
        "taxonomy_version": str(value.get("taxonomy_version") or TAXONOMY_VERSION),
        "dimension_registry_version": str(value.get("dimension_registry_version") or DIMENSION_REGISTRY_VERSION),
        "process_memory_id": str(value.get("process_memory_id") or _id(kind)),
        "kind": kind,
        "task_archetype": [str(item) for item in _list(value.get("task_archetype")) if str(item)] or ["other"],
        "process_dimensions": [str(item) for item in _list(value.get("process_dimensions")) if str(item)],
        "phase": phase,
        "maturity": maturity,
        "outcome": outcome,
        "status": str(value.get("status") or "active"),
        "source_trace_ids": source_trace_ids,
        "verification_evidence": verification,
        "counterevidence": _list(value.get("counterevidence")),
        "preconditions": _list(value.get("preconditions")),
        "repair_actions": _list(value.get("repair_actions")),
        "transfer_scope": dict(value.get("transfer_scope") or {}),
        "model_profile": dict(value.get("model_profile") or {}),
        "environment_fingerprint": dict(value.get("environment_fingerprint") or {}),
        "modality_profile": dict(value.get("modality_profile") or {}),
        "model_capability_fingerprint": dict(value.get("model_capability_fingerprint") or {}),
        "evaluation_set_version": value.get("evaluation_set_version"),
        "drift_status": str(value.get("drift_status") or "stable"),
        "intervention_level": str(value.get("intervention_level") or "hint"),
        "agent": dict(value.get("agent") or {}),
        "primary_context": dict(value.get("primary_context") or {}),
        "related_contexts": _list(value.get("related_contexts")),
        "derived_from": _list(value.get("derived_from")),
        "supersedes": _list(value.get("supersedes")),
        "revalidation_due": value.get("revalidation_due"),
        "selection_exposure": dict(value.get("selection_exposure") or {"shown": 0, "selected": 0, "skipped": 0}),
        "created_at": str(value.get("created_at") or _now()),
        "updated_at": str(value.get("updated_at") or _now()),
    })
    return value


def _verifier_is_independent(item: dict[str, Any]) -> bool:
    kind = str(item.get("verifier_kind") or "")
    status = str(item.get("status") or "").lower()
    scope = str(item.get("scope") or item.get("verification_scope") or "").lower()
    if scope in {"episode_existence_only", "candidate_shape_only", "source_locator_only"}:
        return False
    return kind in INDEPENDENT_VERIFIERS and status in {"passed", "accepted", "verified", "success"}


def _has_verifier(items: list[Any]) -> bool:
    return any(isinstance(item, dict) and _verifier_is_independent(item) for item in items)


def compatibility_match(record: dict[str, Any], compatibility: dict[str, Any] | None) -> bool:
    if not compatibility:
        return True
    model = dict(record.get("model_profile") or {})
    transfer = dict(record.get("transfer_scope") or {})
    requested_family = compatibility.get("model_family") or compatibility.get("family")
    requested_version = compatibility.get("model_version") or compatibility.get("version")
    if transfer.get("transfer_status") == "blocked":
        return False
    if requested_family and model.get("family") != requested_family:
        if transfer.get("model_family") != requested_family or transfer.get("transfer_status") != "verified":
            return False
        if transfer.get("model_version") and requested_version and transfer.get("model_version") != requested_version:
            return False
    elif requested_version and model.get("version") != requested_version:
        return False
    required = set(str(item) for item in compatibility.get("toolchain") or [])
    available = set(str(item) for item in (record.get("environment_fingerprint") or {}).get("toolchain") or [])
    if required and not required.issubset(available):
        return False
    wanted_fp = compatibility.get("capability_fingerprint")
    actual_fp = model.get("capability_fingerprint")
    return not (wanted_fp and actual_fp != wanted_fp)


def compute_intervention(profile: dict[str, Any], task: dict[str, Any] | None) -> dict[str, Any]:
    """Return a task-local intervention decision; policy thresholds are configurable."""
    profile = profile or {}
    failure_evidence = int(profile.get("failure_evidence") or 0)
    confidence = str(profile.get("confidence") or "unknown")
    complexity = str((task or {}).get("complexity") or "normal")
    if confidence == "unknown" and failure_evidence == 0:
        level = "hint"
    elif confidence == "high" and failure_evidence == 0 and complexity != "high":
        level = "hint"
    elif confidence == "unknown" and failure_evidence >= 2 or complexity == "high" and failure_evidence >= 1:
        level = "scaffold"
    else:
        level = "recommend"
    return {"state": "independent" if level == "hint" else ("scaffolded" if level == "scaffold" else "assisted"), "intervention_level": level, "reason": "task_local_capability_policy"}


class ProcessMemoryStore:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and isinstance(value.get("records"), list):
                return value
        except (OSError, ValueError, TypeError):
            pass
        return {"schema": SCHEMA_VERSION, "records": [], "profiles": {}, "updated_at": _now()}

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value["updated_at"] = _now()
        fd, temp = tempfile.mkstemp(prefix="process-memory-", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp, self.path)
        finally:
            try:
                os.unlink(temp)
            except FileNotFoundError:
                pass

    def all(self) -> list[dict[str, Any]]:
        return list(self._read().get("records") or [])

    def _resolve_sources(self, source_ids: list[str]) -> list[dict[str, Any]]:
        records = {str(item.get("process_memory_id")): item for item in self.all()}
        missing = [item for item in source_ids if item not in records]
        if missing:
            raise ValueError("process_memory_source_not_found:" + ",".join(missing))
        return [records[item] for item in source_ids]

    @staticmethod
    def _shared_field(records: list[dict[str, Any]], field: str) -> Any:
        values = [records[0].get(field)] + [item.get(field) for item in records[1:]]
        return values[0] if all(value == values[0] for value in values[1:]) else {}

    def _promoted_payload(self, records: list[dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
        value = dict(payload)
        for field in ("model_profile", "environment_fingerprint", "primary_context"):
            inherited = self._shared_field(records, field)
            if field in value and inherited and value[field] != inherited:
                raise ValueError("process_memory_scope_widening")
            value[field] = inherited
        return value

    def _append(self, record: dict[str, Any]) -> dict[str, Any]:
        data = self._read()
        data["records"].append(record)
        self._write(data)
        return record

    def set_drift_status(self, process_memory_id: str, drift_status: str, verification_evidence: list[Any] | None = None) -> dict[str, Any]:
        if drift_status not in {"stable", "watch", "revalidation_required", "deprecated"}:
            raise ValueError("process_memory_drift_status_invalid")
        data = self._read()
        record = next((item for item in data["records"] if item.get("process_memory_id") == process_memory_id), None)
        if record is None:
            raise ValueError("process_memory_record_not_found")
        evidence = _list(verification_evidence)
        if drift_status == "stable" and not _has_verifier(evidence):
            raise ValueError("revalidation_evidence_required")
        record["drift_status"] = drift_status
        if evidence:
            record["verification_evidence"] = list(record.get("verification_evidence") or []) + evidence
        record["updated_at"] = _now()
        record.setdefault("revalidation_history", []).append({"status": drift_status, "at": record["updated_at"], "evidence": evidence})
        self._write(data)
        return dict(record)

    def set_rollout(self, process_memory_id: str, action: str, *, experiment_id: str | None = None, reason: str = '', baseline: list[Any] | None = None, memory: list[Any] | None = None) -> dict[str, Any]:
        from lib.process_memory_evaluation import evaluate_ab, transfer_gate
        if action not in {'shadow', 'canary', 'publish', 'rollback'}:
            raise ValueError('rollout_action_invalid')
        if action in {'shadow', 'canary'} and not experiment_id:
            raise ValueError('rollout_experiment_required')
        data = self._read()
        record = next((r for r in data['records'] if r.get('process_memory_id') == process_memory_id), None)
        if record is None:
            raise ValueError('process_memory_record_not_found')
        metrics = None
        if action == 'publish':
            metrics = evaluate_ab(baseline or [], memory or [])
            if transfer_gate(metrics)['status'] != 'verified' or record.get('maturity') not in {'verified','replicated','generalized'}:
                raise ValueError('rollout_evaluation_required')
        record['rollout_state'] = {'publish': 'active', 'rollback': 'rolled_back'}.get(action, action)
        record['experiment_id'] = experiment_id
        record.setdefault('rollout_history', []).append({'action': action, 'at': _now(), 'reason': reason, 'experiment_id': experiment_id, 'evaluation': metrics})
        record['updated_at'] = _now()
        self._write(data)
        return dict(record)

    def record_trajectory(self, record: dict[str, Any]) -> dict[str, Any]:
        value = normalize_record({**record, "kind": "trace", "maturity": "observed", "source_trace_ids": record.get("source_trace_ids") or [_id("trace") ]})
        return self._append(value)

    def auto_promote_verified_process(self, *, limit: int = 100) -> dict[str, int]:
        """Automatically derive Episodes and Patterns from verified receipts.

        This is intentionally evidence-driven: no human confirmation is needed,
        but a trace must carry an independent verifier receipt.  The resulting
        records remain shadow/candidate until transfer and rollout gates pass.
        """
        records = self.all()
        episode_sources = {str(source) for row in records if row.get("kind") == "episode" for source in row.get("source_trace_ids") or []}
        added_episodes = 0
        for trace in [row for row in records if row.get("kind") == "trace"][-max(1, int(limit)):]:
            trace_id = str(trace.get("process_memory_id"))
            if trace_id in episode_sources or not _has_verifier(trace.get("verification_evidence") or []):
                continue
            if trace.get("outcome") not in {"correct", "recovered", "partially_correct"}:
                continue
            self.promote_episode(trace_id, {
                "text": f"自动提炼过程事件：{str(trace.get('text') or '')[:2400]}",
                "failure_signature": trace.get("failure_signature") or [],
                "repair_actions": trace.get("repair_actions") or [],
                "verification_evidence": trace.get("verification_evidence") or [],
                "transfer_scope": {"transfer_status": "candidate"},
                "rollout_state": "shadow",
                "auto_derived": True,
            })
            added_episodes += 1
        refreshed = self.all()
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for row in refreshed:
            if row.get("kind") != "episode" or row.get("maturity") not in {"verified", "replicated", "generalized"}:
                continue
            key = tuple(sorted([*(row.get("task_archetype") or ["other"]), *(row.get("process_dimensions") or []), *(row.get("failure_signature") or [])]))
            groups.setdefault(key, []).append(row)
        existing_derived = {tuple(sorted(str(item) for item in (row.get("derived_from") or []))) for row in refreshed if row.get("kind") == "pattern"}
        added_patterns = 0
        for key, episodes in groups.items():
            contexts = {json.dumps(row.get("primary_context") or {}, sort_keys=True) for row in episodes}
            ids = [str(row.get("process_memory_id")) for row in episodes]
            if len(ids) < 2 or len(contexts) < 2 or tuple(sorted(ids)) in existing_derived:
                continue
            self.promote_pattern(ids, {
                "text": "自动提炼可复用过程模式：" + "、".join(key),
                "transfer_scope": {"transfer_status": "candidate"},
                "rollout_state": "shadow",
                "auto_derived": True,
            })
            added_patterns += 1
        return {"episodes": added_episodes, "patterns": added_patterns}

    def record_process_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        value = normalize_record({**observation, "kind": "process_observation", "maturity": "observed", "outcome": observation.get("outcome") or "ambiguous", "source_trace_ids": observation.get("source_trace_ids") or [f"historical:{observation.get('primary_context', {}).get('session_id', 'unknown')}:{observation.get('observation_key', _id('observation'))}"], "intervention_level": "observe"})
        return self._append(value)

    def record_process_draft(self, draft: dict[str, Any]) -> dict[str, Any]:
        """Store an optional short Agent-authored brief without model work."""
        if not isinstance(draft, dict) or not str(draft.get("text") or "").strip():
            raise ValueError("process_draft_text_required")
        if len(str(draft.get("text"))) > 3000:
            raise ValueError("process_draft_too_long")
        if not draft.get("failure_signature") and not draft.get("repair_actions"):
            raise ValueError("process_draft_requires_failure_or_repair")
        if not draft.get("source_trace_ids"):
            raise ValueError("process_draft_source_trace_required")
        value = normalize_record({
            **draft,
            "kind": "process_draft",
            "maturity": "diagnosed",
            "outcome": draft.get("outcome") or "recovered",
            "source_trace_ids": draft.get("source_trace_ids"),
            "process_memory_id": _id("draft"),
            "intervention_level": "observe",
        })
        return self._append(value)

    def promote_episode(self, trace_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        trace = next((item for item in self.all() if item.get("process_memory_id") == trace_id and item.get("kind") == "trace"), None)
        if trace is None:
            raise ValueError("process_memory_trace_not_found")
        evidence = _list(payload.get("verification_evidence"))
        if not _has_verifier(evidence):
            raise ValueError("verification_evidence_required")
        return self._append(normalize_record({**trace, **payload, "kind": "episode", "maturity": "verified", "source_trace_ids": [trace_id], "process_memory_id": _id("episode")}))

    def promote_pattern(self, episode_ids: list[str], payload: dict[str, Any]) -> dict[str, Any]:
        records = self._resolve_sources([str(item) for item in episode_ids])
        if len(records) < 2 or any(item.get("kind") != "episode" or item.get("maturity") not in {"verified", "replicated", "generalized"} for item in records):
            raise ValueError("pattern_requires_verified_episodes")
        traces = [trace_id for item in records for trace_id in item.get("source_trace_ids") or []]
        payload = self._promoted_payload(records, payload)
        return self._append(normalize_record({**payload, "kind": "pattern", "maturity": "replicated", "task_archetype": records[0].get("task_archetype"), "process_dimensions": records[0].get("process_dimensions"), "phase": records[0].get("phase", "reflect"), "outcome": "recovered", "source_trace_ids": sorted(set(traces)), "derived_from": episode_ids, "verification_evidence": [{"verifier_kind": "episode_replication", "status": "passed", "ids": episode_ids}], "process_memory_id": _id("pattern")}))

    def promote_skill(self, pattern_ids: list[str], payload: dict[str, Any]) -> dict[str, Any]:
        records = self._resolve_sources([str(item) for item in pattern_ids])
        if not records or any(item.get("kind") != "pattern" or item.get("maturity") not in {"replicated", "generalized"} for item in records):
            raise ValueError("skill_requires_replicated_patterns")
        traces = [trace_id for item in records for trace_id in item.get("source_trace_ids") or []]
        payload = self._promoted_payload(records, payload)
        return self._append(normalize_record({**payload, "kind": "skill", "maturity": "verified", "task_archetype": records[0].get("task_archetype"), "process_dimensions": records[0].get("process_dimensions"), "phase": records[0].get("phase", "reflect"), "outcome": "correct", "source_trace_ids": sorted(set(traces)), "derived_from": pattern_ids, "verification_evidence": [{"verifier_kind": "pattern_replication", "status": "passed", "ids": pattern_ids}], "process_memory_id": _id("skill")}))

    def record_skill_candidate(self, pattern_ids: list[str], payload: dict[str, Any]) -> dict[str, Any]:
        """Keep a source-backed skill hypothesis visible without making it retrievable.

        Historical imports often contain enough repeated shape to show a useful
        runbook candidate, but not enough independent task verification to publish
        it.  This explicit middle layer prevents the UI from presenting an empty
        skill section while preserving the default search gate (maturity must be
        verified/replicated/generalized and rollout must be active).
        """
        records = self._resolve_sources([str(item) for item in pattern_ids])
        if not records or any(item.get("kind") != "pattern" for item in records):
            raise ValueError("skill_candidate_requires_patterns")
        if any(item.get("maturity") not in {"diagnosed", "replicated", "generalized", "verified"} for item in records):
            raise ValueError("skill_candidate_pattern_maturity_invalid")
        traces = [trace_id for item in records for trace_id in item.get("source_trace_ids") or []]
        inherited = self._shared_field(records, "model_profile")
        if not inherited:
            inherited = {"family": "historical_unknown", "version": "candidate"}
        context = self._shared_field(records, "primary_context")
        if not context:
            context = {"scope": "historical_candidate_cluster"}
        value = normalize_record({
            **payload,
            "kind": "skill",
            "maturity": "diagnosed",
            "status": "candidate",
            "task_archetype": records[0].get("task_archetype"),
            "process_dimensions": sorted({dimension for record in records for dimension in record.get("process_dimensions") or []}),
            "phase": records[0].get("phase", "reflect"),
            "outcome": "ambiguous",
            "source_trace_ids": sorted(set(traces)),
            "derived_from": pattern_ids,
            "verification_evidence": [{"verifier_kind": "source_check", "status": "passed", "scope": "candidate_shape_only", "pattern_ids": pattern_ids}],
            "transfer_scope": {"transfer_status": "unknown"},
            "rollout_state": "shadow",
            "promotion_allowed": False,
            "candidate_reason": "repeated historical pattern shape; independent task verification still required",
            "model_profile": inherited,
            "primary_context": context,
            "process_memory_id": _id("skill_candidate"),
        })
        return self._append(value)

    def search(self, query: str, *, compatibility: dict[str, Any] | None = None, task_archetype: str | None = None, primary_context: dict[str, Any] | None = None, experiment_id: str | None = None, include_unverified: bool = False, limit: int = 8) -> list[dict[str, Any]]:
        terms = [term.lower() for term in str(query or "").split() if term]
        rows = []
        for record in self.all():
            rollout = record.get('rollout_state', 'active')
            if rollout in {'shadow', 'rolled_back'} or (rollout == 'canary' and (not experiment_id or experiment_id != record.get('experiment_id'))):
                continue
            if record.get("status") in {"deprecated", "blocked"} or record.get("drift_status") in {"deprecated", "revalidation_required"}:
                continue
            if not include_unverified and record.get("maturity") not in {"verified", "replicated", "generalized"}:
                continue
            if task_archetype and task_archetype not in (record.get("task_archetype") or []):
                continue
            if primary_context and any((record.get("primary_context") or {}).get(k) != v for k, v in primary_context.items()):
                continue
            if not compatibility_match(record, compatibility):
                continue
            haystack = json.dumps(record, ensure_ascii=False).lower()
            score = sum(1 for term in terms if term in haystack)
            if terms and score == 0:
                continue
            rows.append((score, record))
        rows.sort(key=lambda item: (-item[0], str(item[1].get("updated_at") or "")))
        result = []
        for _, record in rows[: max(1, min(int(limit), 50))]:
            copy = dict(record)
            exposure = dict(copy.get("selection_exposure") or {})
            exposure["shown"] = int(exposure.get("shown") or 0) + 1
            copy["selection_exposure"] = exposure
            result.append(copy)
        return result

    def record_capability_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        if str(observation.get("verifier_kind") or "") == "agent_self_report":
            raise ValueError("capability_verifier_required")
        if not _verifier_is_independent({**observation, "status": observation.get("status") or "passed"}):
            raise ValueError("capability_verifier_required")
        data = self._read()
        version = str(observation.get("model_version") or "")
        key = "|".join(str(observation.get(field) or "unknown") for field in ("model_family", "task_archetype", "phase")) + (f"|{version}" if version else "")
        old = dict(data.get("profiles", {}).get(key) or {"sample_count": 0, "success_count": 0, "failure_count": 0})
        success = str(observation.get("outcome") or "").lower() in {"success", "correct", "passed"}
        old["sample_count"] = int(old.get("sample_count") or 0) + 1
        old["success_count"] = int(old.get("success_count") or 0) + (1 if success else 0)
        old["failure_count"] = int(old.get("failure_count") or 0) + (0 if success else 1)
        n = old["sample_count"]
        rate = old["success_count"] / n
        z = 1.96
        denominator = 1 + z * z / n
        center = (rate + z * z / (2 * n)) / denominator
        margin = z * math.sqrt((rate * (1 - rate) + z * z / (4 * n)) / n) / denominator
        old["confidence_interval"] = [max(0.0, center - margin), min(1.0, center + margin)]
        old["confidence"] = "unknown" if n < 5 else ("high" if old["confidence_interval"][0] >= 0.65 else "medium")
        old.update({"model_family": observation.get("model_family"), "model_version": observation.get("model_version"), "task_archetype": observation.get("task_archetype"), "phase": observation.get("phase"), "last_observed_at": _now(), "time_window": {"start": old.get("time_window", {}).get("start") or _now(), "end": _now()}})
        data.setdefault("profiles", {})[key] = old
        self._write(data)
        result = normalize_record({"kind": "capability_observation", "phase": str(observation.get("phase") or "observe"), "outcome": "correct" if success else "ambiguous", "maturity": "verified", "model_profile": {"family": observation.get("model_family"), "version": observation.get("model_version")}, "task_archetype": [str(observation.get("task_archetype") or "other")], "verification_evidence": [{"verifier_kind": observation.get("verifier_kind"), "status": observation.get("status") or "passed", "scope": observation.get("verification_scope") or "task_result"}], "observation_scope": observation.get("verification_scope") or "task_result", "sample_id": observation.get("sample_id"), "profile": old})
        return self._append(result)

    def capability_profile(self, model_family: str, task_archetype: str, phase: str, model_version: str | None = None) -> dict[str, Any]:
        key = "|".join((str(model_family), str(task_archetype), str(phase))) + (f"|{model_version}" if model_version else "")
        return dict(self._read().get("profiles", {}).get(key) or {"confidence": "unknown", "sample_count": 0, "success_count": 0, "failure_count": 0, "confidence_interval": [0.0, 1.0]})
