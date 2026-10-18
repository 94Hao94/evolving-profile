"""An attributed semantic summary is navigation, never a lossless constraint proof."""


def mark_summary_boundary(value):
    value.update(summary_fidelity='not_certified_lossless',
        constraint_use='original_source_required',guidance_verified=False)
    return value
