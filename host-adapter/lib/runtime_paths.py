"""Resolve colocated Evolving Profile runtime components for Hook entrypoints."""

from __future__ import annotations

from pathlib import Path


def ham_source_root(hook_path: str) -> str:
    """Return the HAM source paired with this Hook, never a historical checkout."""
    root = Path(hook_path).resolve().parent.parent / "ham-os"
    if not (root / "ham" / "adapter.py").is_file():
        raise RuntimeError(f"Evolving Profile HAM source missing beside Hook: {root}")
    return str(root)
