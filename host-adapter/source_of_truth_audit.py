#!/usr/bin/env python3
"""Audit EP source-of-truth files and detect configuration drift."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOME_ROOT = Path.home() / ".evolving-profile"


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return (value if isinstance(value, dict) else None), None if isinstance(value, dict) else "not_object"
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__


def parse_env(path: Path) -> dict[str, str]:
    try:
        return {line.split("=", 1)[0]: line.split("=", 1)[1].strip().strip('"').strip("'") for line in path.read_text().splitlines() if "=" in line and not line.lstrip().startswith("#")}
    except OSError:
        return {}


def audit() -> dict[str, Any]:
    manifest, manifest_error = read_json(ROOT / "config/release-manifest.json")
    runtime, runtime_error = read_json(HOME_ROOT / "config/runtime-settings.json")
    runtime_copy, runtime_copy_error = read_json(HOME_ROOT / "config/release-manifest.json")
    env = parse_env(HOME_ROOT / "profiles/evolving-profile-api.env")
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str, severity: str = "error") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "severity": severity if not ok else "info"})

    check("release_manifest_valid", manifest is not None, manifest_error or "ok")
    check("runtime_settings_valid", runtime is not None, runtime_error or "ok")
    if manifest and runtime_copy:
        check("release_copy_matches_product", manifest.get("product_version") == runtime_copy.get("product_version"), f"repo={manifest.get('product_version')} runtime={runtime_copy.get('product_version')}")
    elif manifest and not runtime_copy:
        check("release_copy_present", False, runtime_copy_error or "missing")
    primary = (runtime or {}).get("providers", {}).get("primary", {}) if runtime else {}
    if primary:
        check("provider_env_model_matches", primary.get("model") == env.get("EVOLVING_PROFILE_API_LLM_MODEL"), f"settings={primary.get('model')} env={env.get('EVOLVING_PROFILE_API_LLM_MODEL')}")
        check("provider_env_base_url_matches", primary.get("base_url") == env.get("EVOLVING_PROFILE_API_LLM_BASE_URL"), "base_url comparison")
        check("provider_key_present", bool(primary.get("api_key") and env.get("EVOLVING_PROFILE_API_LLM_API_KEY")), "key presence only; values never emitted")
    process, process_error = read_json(HOME_ROOT / "process-memory/records.json")
    check("process_memory_valid", process is not None and process.get("schema") == "agent-process-memory.v1", process_error or str((process or {}).get("schema")))
    check("raw_context_present", (Path.home() / ".codex/sessions").is_dir(), "~/.codex/sessions")
    return {"schema": "evolving-profile.source-of-truth-audit.v1", "checks": checks, "ok": all(item["ok"] for item in checks), "authority_count": len((manifest or {}).get("schema_versions", {}))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
