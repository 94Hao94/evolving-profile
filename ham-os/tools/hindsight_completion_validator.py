#!/usr/bin/env python3
"""Hard completion gate for the three-way Hindsight recall repair campaign.

Completion is impossible from service health, a successful replay, a large
candidate count, or a visually plausible status page alone.  Every accepted
case must carry independently produced A/B/C evidence, a Hindsight-only answer,
user-visible trace evidence, claim-level quality gates, and anti-overfit probes.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


REQUIRED_SEAMS = (
    "context_native_answer",
    "bank_exhaustive",
    "production_recall",
    "hindsight_only_answer",
    "status_page_visual",
)
REQUIRED_METRICS = (
    "bank_completeness_passed",
    "retrieval_recall_passed",
    "injection_recall_passed",
    "injection_precision_passed",
    "relation_closure_passed",
    "answer_parity_passed",
    "trace_fidelity_passed",
)
REQUIRED_DIVERSITY = {
    "cross_task_handoff",
    "linked_document_change",
    "recurrence_prevention",
    "entity_relation",
    "open_inventory",
    "timeline_evolution",
    "provenance",
    "observation_mental_model",
    "context_coordination",
    "negative_zero",
    "policy_conflict",
    "graph_constellation",
}
REQUIRED_SUITE_GATES = (
    "source_tests_passed",
    "production_hook_passed",
    "service_health_passed",
    "restart_recovery_passed",
    "rollback_probe_passed",
    "status_page_regression_passed",
    "write_contamination_guard_passed",
)
MIN_CASES = 20
MIN_HOLDOUT = 5


def _check_evidence(
    case_id: str,
    seam: str,
    evidence: dict,
    evidence_root: Path | None,
    failures: list[str],
) -> bool:
    if not bool(evidence.get("passed")):
        return False
    relative = str(evidence.get("evidence_path") or "").strip()
    if not relative:
        failures.append(f"{case_id}: {seam} has no evidence_path")
        return False
    if evidence_root is None:
        return True
    path = (evidence_root / relative).resolve()
    try:
        path.relative_to(evidence_root.resolve())
    except ValueError:
        failures.append(f"{case_id}: {seam} evidence escapes evidence root: {relative}")
        return False
    if not path.is_file():
        failures.append(f"{case_id}: {seam} evidence file missing: {relative}")
        return False
    expected = str(evidence.get("sha256") or "").lower()
    if not expected:
        failures.append(f"{case_id}: {seam} evidence has no sha256")
        return False
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        failures.append(f"{case_id}: {seam} sha256 mismatch: {relative}")
        return False
    return True


def evaluate(manifest: dict, evidence_root: Path | None = None) -> dict:
    cases = list(manifest.get("cases") or [])
    failures: list[str] = []
    passed_cases: list[str] = []
    categories: set[str] = set()
    holdout_passed = 0
    seen_ids: set[str] = set()

    for row in cases:
        case_id = str(row.get("id") or "<missing-id>")
        if case_id in seen_ids:
            failures.append(f"{case_id}: duplicate case id")
            continue
        seen_ids.add(case_id)

        seams = row.get("seams") or {}
        missing = [
            seam
            for seam in REQUIRED_SEAMS
            if not bool((seams.get(seam) or {}).get("passed"))
        ]
        case_failed = bool(missing)
        if missing:
            failures.append(f"{case_id}: missing/failed seams: {', '.join(missing)}")
        for seam in REQUIRED_SEAMS:
            evidence = seams.get(seam) or {}
            if bool(evidence.get("passed")) and not _check_evidence(
                case_id, seam, evidence, evidence_root, failures
            ):
                case_failed = True

        metrics = row.get("metrics") or {}
        failed_metrics = [metric for metric in REQUIRED_METRICS if not bool(metrics.get(metric))]
        if failed_metrics:
            failures.append(f"{case_id}: failed quality gates: {', '.join(failed_metrics)}")
            case_failed = True

        verification = row.get("verification") or {}
        if not bool(verification.get("same_case_replay_passed")):
            failures.append(f"{case_id}: same-case replay is missing or failed")
            case_failed = True
        transfers = list(verification.get("transfer_checks") or [])
        if len(transfers) < 2 or not all(bool(item.get("passed")) for item in transfers):
            failures.append(f"{case_id}: needs at least two passed transfer checks")
            case_failed = True
        if not bool((verification.get("negative_control") or {}).get("passed")):
            failures.append(f"{case_id}: negative control is missing or failed")
            case_failed = True
        if not bool((verification.get("sealed_holdout") or {}).get("passed")):
            failures.append(f"{case_id}: sealed holdout verification is missing or failed")
            case_failed = True

        category = str(row.get("category") or "")
        if not category:
            failures.append(f"{case_id}: category is missing")
            case_failed = True
        if not case_failed:
            passed_cases.append(case_id)
            categories.add(category)
            holdout_passed += int(str(row.get("split") or "") == "holdout")

    missing_categories = sorted(REQUIRED_DIVERSITY - categories)
    if len(passed_cases) < MIN_CASES:
        failures.append(f"need {MIN_CASES} fully evidenced cases; have {len(passed_cases)}")
    if holdout_passed < MIN_HOLDOUT:
        failures.append(f"need {MIN_HOLDOUT} unseen holdout cases; have {holdout_passed}")
    if missing_categories:
        failures.append("missing diversity categories: " + ", ".join(missing_categories))

    suite_gates = manifest.get("suite_gates") or {}
    failed_suite_gates = [gate for gate in REQUIRED_SUITE_GATES if not bool(suite_gates.get(gate))]
    if failed_suite_gates:
        failures.append("failed suite gates: " + ", ".join(failed_suite_gates))

    return {
        "schema": "hindsight.three-way-completion-validator.v2",
        "passed_cases": passed_cases,
        "passed_count": len(passed_cases),
        "holdout_passed": holdout_passed,
        "missing_categories": missing_categories,
        "complete": not failures,
        "failures": failures,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: hindsight_completion_validator.py MANIFEST.json", file=sys.stderr)
        return 2
    path = Path(sys.argv[1]).resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"complete": False, "failures": [f"cannot read manifest: {error}"]}, ensure_ascii=False))
        return 2
    result = evaluate(manifest, evidence_root=path.parent)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
