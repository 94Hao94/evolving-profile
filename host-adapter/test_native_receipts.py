import json
from pathlib import Path


def _receipt(host: str = "trae", capability: str = "mcp_stdio") -> dict:
    return {
        "host_id": host,
        "capability_id": capability,
        "probe_id": f"probe-{host}-{capability}",
        "observed_at": "2026-11-08T00:00:00Z",
        "state": "host_verified",
        "evidence_kind": "native_host",
        "installation_id": f"{host}@test",
    }


def test_append_native_receipt_updates_history_latest_and_event_stream(tmp_path: Path) -> None:
    from lib.host_integration.native_receipts import append_native_receipt, read_latest_native_receipts

    first = append_native_receipt(tmp_path, _receipt())
    assert first["state"] == "host_verified"

    history = json.loads((tmp_path / "host-integrations/native-receipts.json").read_text())
    latest = json.loads((tmp_path / "host-integrations/native-receipts-latest.json").read_text())
    events = (tmp_path / "host-integrations/native-receipt-events.jsonl").read_text().splitlines()

    assert len(history["receipts"]) == 1
    assert len(latest["receipts"]) == 1
    assert len(events) == 1
    assert read_latest_native_receipts(tmp_path)[0]["probe_id"] == first["probe_id"]


def test_append_native_receipt_keeps_newer_projection_for_same_key(tmp_path: Path) -> None:
    from lib.host_integration.native_receipts import append_native_receipt, read_latest_native_receipts

    append_native_receipt(tmp_path, _receipt())
    newer = _receipt()
    newer.update({"probe_id": "probe-new", "observed_at": "2026-11-08T01:00:00Z"})
    append_native_receipt(tmp_path, newer)

    latest = read_latest_native_receipts(tmp_path)
    assert len(latest) == 1
    assert latest[0]["probe_id"] == "probe-new"

