"""Read-only baseline inventory and explicit non-publishing dispositions."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import urllib.parse
import urllib.request


def build_disposition_manifest(observations: list[dict], models: list[dict], *, bank_id: str, snapshot_revision: str) -> dict:
    dispositions = []
    for item in observations:
        dispositions.append({"input_kind": "observation", "input_id": item["id"], "source_revision": item.get("updated_at") or snapshot_revision,
                             "status": "held_pending_source_review", "reason": "baseline_not_promoted_without_source_and_scope_review", "guidance_publication": None})
    for item in models:
        dispositions.append({"input_kind": "mental_model", "input_id": item["id"], "source_revision": item.get("updated_at") or snapshot_revision,
                             "status": "held_pending_source_review", "reason": "model_sections_require_source_dependency_revalidation", "guidance_publication": None})
    return {"schema": "guidance.migration-manifest.v1", "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "bank_id": bank_id,
            "snapshot_revision": snapshot_revision, "input_count": len(dispositions), "dispositions": dispositions,
            "summary": {"active_from_baseline": 0, "held_pending_source_review": len(dispositions)},
            "boundary": "This is a complete baseline disposition inventory, not a claim that each held item has been semantically re-reviewed or published."}


def _get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=30) as response:
        return json.loads(response.read())


def fetch_baseline(api_url: str, bank_id: str) -> tuple[list[dict], list[dict]]:
    encoded = urllib.parse.quote(bank_id, safe="")
    observations = _get(api_url, "/v1/default/banks/" + encoded + "/memories/list?type=observation&limit=1000&offset=0").get("items") or []
    models = _get(api_url, "/v1/default/banks/" + encoded + "/mental-models?detail=metadata&limit=1000&offset=0").get("items") or []
    if len({row.get("id") for row in observations}) != len(observations) or len({row.get("id") for row in models}) != len(models):
        raise ValueError("duplicate_baseline_ids")
    return observations, models


def write_baseline_manifest(output_path: str | Path, api_url: str, bank_id: str) -> dict:
    observations, models = fetch_baseline(api_url, bank_id)
    manifest = build_disposition_manifest(observations, models, bank_id=bank_id,
                                          snapshot_revision="inventory:" + dt.datetime.now(dt.timezone.utc).isoformat())
    path = Path(output_path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
