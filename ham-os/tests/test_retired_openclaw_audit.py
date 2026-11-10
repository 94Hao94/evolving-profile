"""Regression guard: a retired adapter must not hold the active platform unhealthy."""
from pathlib import Path


AUDIT = Path.home() / ".hindsight" / "bin" / "hindsight-operational-audit.py"


def test_operational_audit_does_not_require_retired_openclaw_runtime():
    source = AUDIT.read_text(encoding="utf-8")
    assert '("openclaw", "http://127.0.0.1:18789/", {200})' not in source
    assert '"ai.openclaw.gateway",' not in source
    assert 'openclaw-lark:package-missing' not in source
    assert 'openclaw-tail-flush:session-end-hook-missing' not in source
