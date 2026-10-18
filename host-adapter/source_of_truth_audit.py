#!/usr/bin/env python3
"""Audit EP source-of-truth files and detect configuration drift."""
from __future__ import annotations

import argparse
import json
import os
import re
import hashlib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HOME_ROOT = Path.home() / ".evolving-profile"


def audit_runtime_code(source_root, runtime_root, *, components=None):
    """Compare complete declared production Python trees, never execute them.

    Roots must be the approved deployment source and its installed copy, not
    a sanitized template versus personal code. This is disk parity only, not
    proof of loaded processes, dependencies, configuration or data quality.
    """
    source=Path(source_root).expanduser().resolve();runtime=Path(runtime_root).expanduser().resolve()
    components=components if components is not None else ['host-adapter','guidance','controller','status']
    errors=[];rows=[];mismatches=[]
    if source==runtime:errors.append({'reason':'independent_source_required'})
    ignored={'__pycache__','.venv','node_modules','.git','tests'}
    def files(root):
        result={}
        if not root.is_dir():errors.append({'side':'runtime' if root==runtime else 'source','reason':'root_unavailable'});return result
        for component in components:
            relative=Path(component)
            if relative.is_absolute() or '..' in relative.parts or not relative.parts:
                errors.append({'reason':'invalid_component'});continue
            folder=root/relative
            if not folder.is_dir() or folder.is_symlink() or not folder.resolve().is_relative_to(root):
                errors.append({'component':str(relative),'reason':'component_unavailable'});continue
            for directory,dirs,names in os.walk(folder,followlinks=False,onerror=lambda _:errors.append({'reason':'directory_enumeration_failed'})):
                for name in list(dirs):
                    candidate=Path(directory)/name
                    if name in ignored or candidate.is_symlink():
                        dirs.remove(name)
                        if name not in ignored:errors.append({'reason':'symlink_directory_unverified'})
                for name in names:
                    if not name.endswith('.py') or name.startswith('test_') or name=='conftest.py':continue
                    path=Path(directory)/name;key=str(path.relative_to(root))
                    if path.is_symlink():errors.append({'path':key,'reason':'symlink_file_unverified'});continue
                    if not path.is_file():errors.append({'path':key,'reason':'nonregular_file_unverified'});continue
                    result[key]=path
                    if len(result)>2048:errors.append({'reason':'code_file_count_exceeded'});return result
        return result
    def digest(path):
        try:
            h=hashlib.sha256();used=0
            with path.open('rb') as stream:
                while block:=stream.read(65536):
                    used+=len(block)
                    if used>8*1024*1024:raise ValueError('code_file_budget_exceeded')
                    h.update(block)
            return h.hexdigest()
        except (OSError,ValueError):
            errors.append({'reason':'code_file_unreadable_or_oversized'});return None
    a,b=files(source),files(runtime)
    if not a:errors.append({'reason':'no_approved_code_files'})
    for path in sorted(set(a)|set(b)):
        left=digest(a[path]) if path in a else None;right=digest(b[path]) if path in b else None
        reason='unexpected_runtime_file' if path not in a else 'missing_runtime_file' if path not in b else 'content_changed' if left!=right else None
        rows.append({'path':path,'source_sha256':left,'runtime_sha256':right})
        if reason:mismatches.append({'path':path,'reason':reason})
    return {'schema':'evolving-profile.runtime-code-parity.v1',
        'status':'unavailable' if errors else 'drift' if mismatches else 'matched',
        'coverage':'declared_production_python_trees','components':components,
        'files':rows,'mismatches':mismatches,'errors':errors,
        'limitations':['Test/cache code, third-party dependencies, settings/data and already-loaded process modules are not certified.']}


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
        def product_version(value):
            match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", str(value))
            return tuple(int(part or 0) for part in match.groups()) if match else value
        check("release_copy_matches_product", product_version(manifest.get("product_version")) == product_version(runtime_copy.get("product_version")), f"repo={manifest.get('product_version')} runtime={runtime_copy.get('product_version')}")
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
    parser.add_argument('--code-source',type=Path)
    parser.add_argument('--code-runtime',type=Path)
    parser.add_argument('--code-component',action='append')
    args = parser.parse_args()
    if args.code_source is not None or args.code_runtime is not None:
        if args.code_source is None or args.code_runtime is None:parser.error('Both --code-source and --code-runtime are required')
        result=audit_runtime_code(args.code_source,args.code_runtime,components=args.code_component)
        print(json.dumps(result,ensure_ascii=False,indent=None if args.json else 2))
        return 0 if result['status']=='matched' else 1 if result['status']=='drift' else 2
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
