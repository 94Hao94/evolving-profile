import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tools" / "ham_canary_gate.py"


def load_gate_module():
    spec = importlib.util.spec_from_file_location("ham_canary_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_interim_release_gate_accepts_the_existing_sealed_10_case_protocol():
    gate = load_gate_module()
    result = gate.evaluate_gate(
        hidden={"total": 10, "passed": 10, "overall_pass": True},
        isolation={"pollution_free": True, "repetitions": 3},
        restore={"status": "passed", "production_routing_changed": False},
        live_e2e=[
            {"url": "http://127.0.0.1:8879/health", "status": 200},
            {"url": "http://127.0.0.1:8888/health", "status": 200},
            {"url": "http://127.0.0.1:9998/api/status", "status": 200},
        ],
    )

    assert result["schema"] == "ham.phase6.release_gate.v2"
    assert result["gates"]["sealed_hidden_minimum"] is True
    assert result["gates"]["abc_isolation"] is True
    assert result["gates"]["restore_drill"] is True
    assert result["gates"]["live_end_to_end"] is True
    assert result["eligible"] is True
    assert result["benchmark_debt"]["target_cases"] == 255
    assert result["benchmark_debt"]["remaining_cases"] == 245


def test_interim_release_gate_does_not_accept_partial_hidden_suite():
    gate = load_gate_module()
    result = gate.evaluate_gate(
        hidden={"total": 10, "passed": 9, "overall_pass": False},
        isolation={"pollution_free": True, "repetitions": 3},
        restore={"status": "passed", "production_routing_changed": False},
        live_e2e=[
            {"url": "http://127.0.0.1:8879/health", "status": 200},
            {"url": "http://127.0.0.1:8888/health", "status": 200},
            {"url": "http://127.0.0.1:9998/api/status", "status": 200},
        ],
    )

    assert result["gates"]["sealed_hidden_minimum"] is False
    assert result["eligible"] is False
