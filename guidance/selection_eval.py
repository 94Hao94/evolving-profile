"""Small, auditable evaluation helpers for selector replay sets."""
from __future__ import annotations


def score_cases(cases: list[dict]) -> dict:
    """Compute precision/recall/abstention from human-labelled cases.

    Each case has ``expected`` and ``selected`` sets of stable guidance IDs.
    ``expected=[]`` is a legitimate abstention case.
    """
    tp = fp = fn = abstain_correct = 0
    for case in cases:
        expected = set(case.get("expected") or [])
        selected = set(case.get("selected") or [])
        tp += len(expected & selected)
        fp += len(selected - expected)
        fn += len(expected - selected)
        if not expected and not selected:
            abstain_correct += 1
    labelled = len(cases)
    return {
        "cases": labelled,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": round(tp / (tp + fp), 4) if tp + fp else 1.0,
        "recall": round(tp / (tp + fn), 4) if tp + fn else 1.0,
        "abstention_accuracy": round(abstain_correct / labelled, 4) if labelled else 0.0,
        "empty_expected_cases": sum(not (case.get("expected") or []) for case in cases),
    }


def build_case(prompt: str, expected: list[str], selected: list[str], *, note: str = "") -> dict:
    return {"prompt": prompt, "expected": sorted(set(expected)), "selected": sorted(set(selected)), "note": note}


def score_reviewed_cases(cases: list[dict]) -> dict:
    """Score human-reviewed must/optional/must-not labels.

    Optional items count as acceptable selections but are not required for
    recall. Explicit negatives count as false positives. Duplicate selections
    are reported separately rather than inflating precision.
    """
    tp = fp = fn = 0
    valid_empty = 0
    selected_total = duplicate_total = 0
    stale_total = stale_suppressed = conflict_total = conflict_suppressed = 0
    for case in cases:
        must = set(case.get("must_select") or [])
        optional = set(case.get("optional") or [])
        forbidden = set(case.get("must_not") or [])
        raw_selected = list(case.get("selected") or [])
        selected = set(raw_selected)
        selected_total += len(raw_selected)
        duplicate_total += len(raw_selected) - len(selected)
        tp += len(selected & must)
        fp += len((selected - must - optional) | (selected & forbidden))
        fn += len(must - selected)
        if case.get("valid_empty") and not selected:
            valid_empty += 1
        stale = set(case.get("stale_ids") or [])
        conflicts = set(case.get("conflict_ids") or [])
        stale_total += len(stale); stale_suppressed += len(stale - selected)
        conflict_total += len(conflicts); conflict_suppressed += len(conflicts - selected)
    count = len(cases)
    return {
        "cases": count, "true_positive": tp, "false_positive": fp, "false_negative": fn,
        "precision": round(tp / (tp + fp), 4) if tp + fp else 1.0,
        "recall": round(tp / (tp + fn), 4) if tp + fn else 1.0,
        "abstention_accuracy": round(valid_empty / count, 4) if count else 0.0,
        "duplicate_rate": (duplicate_total / selected_total) if selected_total else 0.0,
        "stale_suppression": stale_suppressed / stale_total if stale_total else 1.0,
        "conflict_suppression": conflict_suppressed / conflict_total if conflict_total else 1.0,
        "label_state": "human_reviewed",
    }
