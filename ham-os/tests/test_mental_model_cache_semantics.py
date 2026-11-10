import importlib.util
from pathlib import Path

AUDIT = Path.home() / '.hindsight' / 'bin' / 'hindsight-operational-audit.py'


def load_audit():
    spec = importlib.util.spec_from_file_location('hindsight_operational_audit', AUDIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cache_staleness_uses_refresh_due_not_any_pending_observation():
    audit = load_audit()
    assert audit.derive_mental_model_stale(semantic_pending=3, refresh_threshold=8, oldest_age_hours=0, max_age_hours=24) is False
    assert audit.derive_mental_model_stale(semantic_pending=8, refresh_threshold=8, oldest_age_hours=0, max_age_hours=24) is True
