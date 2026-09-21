#!/usr/bin/env python3
"""Read-only PRD 2.0 acceptance snapshot.

Checks live services, route behavior, and deployed UI API surfaces. It does
not publish memory, invoke retention, or infer answer-side adoption.
"""
from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request


STATUS = "http://127.0.0.1:12098"
CONSOLE = "http://127.0.0.1:9999"


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=8) as response:
        return json.loads(response.read())


def main() -> int:
    checks = []
    memory_map = get(f"{STATUS}/api/guidance/memory-map")
    checks.append({"id": "memory-map-layers", "passed": [x["id"] for x in memory_map["layers"]] == ["L0", "L1", "L2"]})
    nodes = {node["id"]: node for node in memory_map["nodes"]}
    checks.append({"id": "live-bank-counts", "passed": all(nodes[name].get("count") is not None for name in ("world", "experience", "entities", "observations"))})

    cases = [("Evolving Profile 2.0 PRD", "recall"), ("回顾之前项目的时间线、实体冲突和原始来源", "research"), ("请回读记忆 fbf6ead8-8696-4adc-8331-25f23bfbca5e 的原文出处和版本", "read_source"), ("把这段文字改成三句话", "skip")]
    for prompt, expected in cases:
        value = get(f"{STATUS}/api/guidance/memory-check?q={urllib.parse.quote(prompt)}")
        checks.append({"id": f"route:{expected}", "passed": value.get("recommended_route") == expected, "actual": value.get("recommended_route")})

    prompt_page = get(f"{CONSOLE}/api/evolving-profile/guidance/prompts?limit=1&cursor=0&host=all")
    checks.append({"id": "prompt-route-receipt", "passed": bool(prompt_page.get("items") and "memory_route_receipt" in prompt_page["items"][0])})
    mcp = subprocess.run(["/Applications/ChatGPT.app/Contents/Resources/codex", "mcp", "list"], capture_output=True, text=True, timeout=8)
    checks.append({"id": "controller-registration", "passed": "evolving_profile_controller" in mcp.stdout})
    result = {"schema": "evolving-profile.prd-2-audit.v1", "checks": checks, "passed": sum(bool(x["passed"]) for x in checks), "total": len(checks)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] == result["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
