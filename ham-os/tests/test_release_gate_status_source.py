"""The LaunchAgent must read the gate from a TCC-accessible control-plane path."""
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "control" / "hindsight_rebuild_status_server.py"


def test_status_server_reads_release_gate_outside_documents_folder():
    source = SOURCE.read_text(encoding="utf-8")
    assert "HAM_RELEASE_GATE=HOME/'.hindsight/control-plane/ham-os-release-gate.json'" in source
    assert "phase6-canary-gate.json" not in source
