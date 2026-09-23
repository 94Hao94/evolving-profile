"""Evidence and lifecycle scoring for multi-dimensional preference candidates.

Pure functions only: this module never publishes or mutates the registry.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityInput:
    kind: str = "inferred"
    independent_threads: int = 0
    source_families: int = 0
    support_count: int = 0
    contradiction_count: int = 0
    user_corrections: int = 0
    age_days: float = 0.0
    explicit_scope: bool = False


def evidence_confidence(value: QualityInput) -> float:
    """Conservative, explainable confidence; intentionally not an LLM score."""
    if value.user_corrections:
        return 0.0
    base = 0.45 if value.kind == "explicit" else 0.15
    base += min(value.independent_threads, 4) * 0.08
    base += min(value.source_families, 4) * 0.06
    base += min(value.support_count, 6) * 0.03
    base -= min(value.contradiction_count, 4) * 0.12
    if value.explicit_scope:
        base += 0.05
    # Soft freshness decay; temporal validity still belongs to the record.
    base -= min(max(value.age_days, 0.0) / 365.0, 0.25)
    return round(max(0.0, min(1.0, base)), 4)


def lifecycle_state(value: QualityInput) -> str:
    if value.user_corrections:
        return "retracted"
    if value.contradiction_count > value.support_count:
        return "needs_review"
    if value.kind == "explicit" and value.support_count >= 1:
        return "reviewable_preference"
    if value.independent_threads >= 2 and value.source_families >= 2 and value.support_count >= 2:
        return "reviewable_preference"
    return "observation_candidate"


def should_activate(value: QualityInput) -> bool:
    return lifecycle_state(value) == "reviewable_preference" and evidence_confidence(value) >= 0.55
