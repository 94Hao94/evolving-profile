#!/usr/bin/env python3
"""Plan or apply bounded refresh repairs once per mental model.

The default mode is read-only planning. ``--apply`` executes at most one
fingerprint-gated repair per mental model; the domain processor supersedes
duplicate failed refreshes for that model and writes its own recovery receipt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

from evolving_profile_api.engine.repair_service import RepairService, save_repair_plan


def _clean(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return str(value)


def _http_json(url: str, body: dict[str, Any] | None = None, timeout: int = 180) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode() or "{}")


async def _failed_operations(database_url: str, bank_id: str, max_models: int | None) -> list[dict[str, Any]]:
    connection = await asyncpg.connect(database_url)
    try:
        limit = "" if max_models is None else " LIMIT $1"
        args = () if max_models is None else (max_models,)
        rows = await connection.fetch(
            f"""
            SELECT DISTINCT ON (result_metadata->>'mental_model_id')
                operation_id, bank_id, operation_type, status, error_message,
                result_metadata, task_payload
            FROM public.async_operations
            WHERE operation_type = 'refresh_mental_model'
              AND status = 'failed'
              AND result_metadata->>'repair_recommended' = 'true'
              AND result_metadata->>'mental_model_id' IS NOT NULL
            ORDER BY result_metadata->>'mental_model_id', updated_at DESC
            {limit}
            """,
            *args,
        )
        return [_clean(dict(row)) for row in rows]
    finally:
        await connection.close()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-id", default="ep-default-bank-v2-shadow-20260811")
    parser.add_argument("--api", default="http://127.0.0.1:12088")
    parser.add_argument("--max-models", type=int, default=None)
    parser.add_argument("--apply", action="store_true", help="execute bounded repairs; omit for preview only")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    database_url = os.environ.get("EVOLVING_PROFILE_API_DATABASE_URL")
    if not database_url:
        env_path = Path.home() / ".evolving-profile/profiles/evolving-profile-api.env"
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("EVOLVING_PROFILE_API_DATABASE_URL="):
                database_url = line.split("=", 1)[1].strip()
                break
    if not database_url:
        raise SystemExit("EVOLVING_PROFILE_API_DATABASE_URL is required")

    rows = await _failed_operations(database_url, args.bank_id, args.max_models)
    results: list[dict[str, Any]] = []
    for index, operation in enumerate(rows, 1):
        operation_id = str(operation["operation_id"])
        status, normalized = _http_json(
            f"{args.api}/v1/default/banks/{args.bank_id}/operations/{operation_id}?include_payload=true",
            timeout=30,
        )
        if status != 200:
            results.append({"operation_id": operation_id, "status": "operation_status_error", "http_status": status})
            continue
        fingerprint = RepairService.fingerprint(normalized)
        plan = RepairService().diagnose(
            bank_id=args.bank_id,
            incident_id=f"repair-refresh-wave-{datetime.now(timezone.utc).date().isoformat()}-{index}",
            source_id=operation_id,
            operation=normalized,
            source_fingerprint=fingerprint,
            target_version="current",
        )
        plan_path = save_repair_plan(plan)
        result: dict[str, Any] = {
            "operation_id": operation_id,
            "mental_model_id": (normalized.get("result_metadata") or {}).get("mental_model_id"),
            "repair_id": plan.repair_id,
            "plan_path": str(plan_path),
            "status": "preview_ready",
        }
        if args.apply:
            apply_status, applied = _http_json(
                f"{args.api}/v1/default/banks/{args.bank_id}/repairs/{plan.repair_id}/apply",
                {"confirmed": True, "current_source_fingerprint": fingerprint, "current_target_version": "current"},
            )
            result.update({"status": applied.get("status", "apply_failed"), "http_status": apply_status, "apply_receipt": applied.get("apply_receipt")})
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    receipt = {"schema": "ep.refresh-repair-wave.v1", "bank_id": args.bank_id, "apply": args.apply, "models": results}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all(item.get("status") in {"preview_ready", "applied"} for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
