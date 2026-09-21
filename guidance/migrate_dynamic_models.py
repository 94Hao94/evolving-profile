"""Migrate fixed domain aggregates into atomic cross-dimensional models."""
from __future__ import annotations

import argparse
import datetime as dt
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time

from mcp_runtime import load_repository
from models import validate_atomic_model
from repository import GuidanceRepository


SECTION_TITLES = {
    "authority-and-scope": "先确认权威来源与任务边界",
    "memory-routing": "按证据缺口选择记忆路线",
    "agent-boundaries": "主智能体保留核心判断与授权边界",
    "objective-and-constraints": "先锁定目标、阶段与约束",
    "change-impact": "修改前识别影响范围并做同类回归",
    "evidence-and-conflict": "以证据、范围和时间处理冲突",
    "analysis-and-recommendation": "从证据缺口形成有排序的建议",
    "business-language": "用真实业务逻辑组织正式表达",
    "mechanism-first": "先重建机制和因果链",
    "examples-and-analogy": "按陌生度选择例子和有边界类比",
    "transfer-check": "以复述和迁移验证理解",
    "execution-control": "授权明确后连续推进并守住边界",
    "artifact-quality": "按真实使用场景验收交付物",
    "verification-and-recovery": "用可见证据验收并保留回退",
    "additional-active-patterns": "旧领域汇总中的其他活动模式",
}


def _revision(payload: dict) -> str:
    clean = {key: value for key, value in payload.items() if key != "revision"}
    return "sha256:" + sha256(json.dumps(clean, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _atomic_id(section: dict) -> str:
    mechanism = " ".join(str(section.get("text") or "").split()).casefold()
    return "mental-model:" + sha256(mechanism.encode()).hexdigest()[:24]


def _candidate(parent: dict, section: dict, units: dict[tuple[str, str], dict], verified_at: str) -> dict:
    refs = []
    for ref in section.get("guidance_refs") or []:
        key = (str(ref.get("id") or ""), str(ref.get("revision") or ""))
        if key in units and key not in {(value["id"], value["revision"]) for value in refs}:
            refs.append({"id": key[0], "revision": key[1]})
    dimensions = sorted({str(units[(ref["id"], ref["revision"])].get("primary_category") or "") for ref in refs} - {""})
    section_id = str(section.get("section_id") or "mechanism")
    hold_reasons = []
    if len(dimensions) < 2:
        hold_reasons.append("requires_two_dimensions")
    if len(refs) < 2:
        hold_reasons.append("requires_two_references")
    if section_id == "additional-active-patterns":
        hold_reasons.append("legacy_catch_all")
    if not section.get("applies_when") or not (section.get("exceptions") or section.get("counterevidence")):
        hold_reasons.append("missing_scope_or_counterevidence")
    active = not hold_reasons
    model_section = {
        "section_id": "mechanism",
        "text": str(section.get("text") or "").strip(),
        "applies_when": list(section.get("applies_when") or []),
        "exceptions": list(section.get("exceptions") or []),
        "guidance_refs": refs,
        "counterevidence": list(section.get("counterevidence") or []),
    }
    payload = {
        "id": _atomic_id(section),
        "model_kind": "atomic_cross_dimensional" if active else "atomic_cross_dimensional_candidate",
        "status": "active" if active else "needs_review",
        "title": SECTION_TITLES.get(section_id, section_id.replace("-", " ")),
        "purpose": "把多个偏好维度组合成一个可复用的判断或行动机制。",
        "mechanism": model_section["text"],
        "dimensions": dimensions,
        "confidence": 0.85 if active else 0.6,
        "last_verified_at": verified_at,
        "hold_reasons": hold_reasons,
        "legacy_source": {"model_id": parent["id"], "model_revision": parent.get("revision"), "section_id": section_id},
        "sections": [model_section],
    }
    payload["revision"] = _revision(payload)
    return payload


def build_migration(repo: GuidanceRepository, *, verified_at: str = "2026-09-16T00:00:00+00:00") -> dict:
    active_units = repo.active_units()
    units = {(unit["id"], unit["revision"]): unit for unit in active_units}
    legacy = [model for model in repo.active_models() if not model.get("model_kind")]
    candidates = [_candidate(model, section, units, verified_at) for model in legacy for section in model.get("sections") or []]
    # Equivalent mechanisms from multiple legacy aggregates collapse to one ID.
    unique = {}
    for candidate in candidates:
        prior = unique.get(candidate["id"])
        if prior is None or (prior["status"] != "active" and candidate["status"] == "active"):
            unique[candidate["id"]] = candidate
    candidates = list(unique.values())
    return {
        "schema": "evolving-profile.dynamic-model-migration.v1",
        "active": [model for model in candidates if model["status"] == "active"],
        "candidates": [model for model in candidates if model["status"] == "needs_review"],
        "legacy_ids": sorted(model["id"] for model in legacy),
    }


def apply_migration(repo: GuidanceRepository, migration: dict | None = None) -> dict:
    migration = migration or build_migration(repo)
    for model in migration["active"]:
        validate_atomic_model(repo, model)
    with repo.transaction() as db:
        now = time.time()
        for model_id in migration["legacy_ids"]:
            db.execute("UPDATE model_revisions SET active=0 WHERE model_id=? AND active=1", (model_id,))
        for model in migration["active"]:
            db.execute("UPDATE model_revisions SET active=0 WHERE model_id=?", (model["id"],))
            db.execute("INSERT INTO model_revisions(model_id,revision,payload_json,active,created_at) VALUES(?,?,?,?,?) ON CONFLICT(model_id,revision) DO UPDATE SET payload_json=excluded.payload_json,active=1,created_at=excluded.created_at",
                       (model["id"], model["revision"], json.dumps(model, ensure_ascii=False), 1, now))
        for model in migration["candidates"]:
            db.execute("INSERT INTO model_revisions(model_id,revision,payload_json,active,created_at) VALUES(?,?,?,?,?) ON CONFLICT(model_id,revision) DO UPDATE SET payload_json=excluded.payload_json,active=0,created_at=excluded.created_at",
                       (model["id"], model["revision"], json.dumps(model, ensure_ascii=False), 0, now))
        repo._set_meta("dynamic_model_schema", "atomic-cross-dimensional.v1", db)
        repo._set_meta("legacy_model_archive", json.dumps({"model_ids": migration["legacy_ids"], "reason": "fixed_domain_aggregate_replaced", "archived_at": now}, ensure_ascii=False), db)
    inventory = repo.model_inventory()
    expected = {"active": len(migration["active"]), "candidates": len(migration["candidates"]), "archived_legacy": len(migration["legacy_ids"])}
    if inventory["counts"] != expected:
        raise RuntimeError(f"migration_count_mismatch:{inventory['counts']}!={expected}")
    return inventory


def backup_registry(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", default="")
    args = parser.parse_args()
    repo = load_repository(args.config)
    migration = build_migration(repo, verified_at=dt.datetime.now(dt.timezone.utc).isoformat())
    result = {"planned": {key: len(migration[key]) for key in ("active", "candidates", "legacy_ids")}}
    if args.apply:
        backup_dir = Path(args.backup_dir or Path(repo.path).parent / "migration-backups")
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = backup_registry(repo.path, backup_dir / f"guidance-before-dynamic-models-{stamp}.sqlite3")
        inventory = apply_migration(repo, migration)
        result.update(backup=str(backup), counts=inventory["counts"])
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
