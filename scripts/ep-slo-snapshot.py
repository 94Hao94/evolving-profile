#!/usr/bin/env python3
"""Capture a bounded SLO snapshot from live EP services."""

from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def metric_snapshot() -> dict:
    with urllib.request.urlopen("http://127.0.0.1:12088/metrics", timeout=10) as response:
        text = response.read().decode("utf-8", "replace")
    wanted = {}
    for line in text.splitlines():
        if line.startswith("hindsight_http_requests_total{") or line.startswith("hindsight_http_duration_seconds_"):
            if "endpoint=\"/v1/default/banks/{bank_id}/memories/recall\"" in line or "endpoint=\"/v1/default/banks/{bank_id}/memories\"" in line or "endpoint=\"/health\"" in line:
                key = line.split(" ", 1)[0]
                value = line.split()[-1]
                wanted[key] = float(value)
    return wanted


def rss_snapshot() -> list[dict]:
    rows = []
    output = subprocess.check_output(["ps", "-axo", "pid=,rss=,command="], text=True)
    for line in output.splitlines():
        match = re.match(r"\s*(\d+)\s+(\d+)\s+(.*)", line)
        if not match:
            continue
        pid, rss, command = match.groups()
        if any(token in command for token in ("evolving_profile_api.main", "evolving_profile_api.worker.main", "/runtime/controller/controller.py")):
            rows.append({"pid": int(pid), "rss_bytes": int(rss) * 1024, "command": command[:300]})
    return rows


def main() -> int:
    state_root = Path("/Users/example/.evolving-profile")
    queue_path = state_root / "codex/state/retention-queue.json"
    queue = json.loads(queue_path.read_text()) if queue_path.exists() else {"items": []}
    controller = get_json("http://127.0.0.1:12079/v1/status")
    result = {
        "schema": "ep.slo-snapshot.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "services": {
            "api": get_json("http://127.0.0.1:12088/health"),
            "worker": get_json("http://127.0.0.1:12089/health"),
            "controller": get_json("http://127.0.0.1:12079/health"),
        },
        "controller_counters": {key: controller.get(key) for key in ("errors", "recalls", "plans", "active_reads", "functional_status")},
        "http_metrics": metric_snapshot(),
        "processes": rss_snapshot(),
        "retention": {
            "queue_items": len(queue.get("items", [])),
            "quarantined_items": sum(bool(row.get("retention_quarantine")) for row in queue.get("items", [])),
            "held_items": sum(bool(row.get("retention_origin_hold")) for row in queue.get("items", [])),
        },
        "window": "current_export_snapshot; historical percentile storage requires a metrics backend",
    }
    output = state_root / "audit/slo-snapshot.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    output.chmod(0o600)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

