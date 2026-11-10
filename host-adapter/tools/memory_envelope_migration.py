"""Preview or apply the additive process-memory envelope migration.

Default mode is read-only. ``--apply`` writes one timestamped backup and only
adds/refreshes ``memory_envelope``; it does not change process taxonomy,
source traces, outcome or maturity fields.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from lib.process_memory import normalize_record


def run(path: Path, *, apply: bool = False) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("records") or []
    changed = 0
    invalid = []
    updated = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            invalid.append({"index": index, "reason": "record_not_object"})
            continue
        try:
            normalized = normalize_record(row)
        except (TypeError, ValueError) as exc:
            invalid.append({"index": index, "id": row.get("process_memory_id"), "reason": str(exc)})
            continue
        if row.get("memory_envelope") != normalized.get("memory_envelope"):
            changed += 1
            updated.append((index, normalized["memory_envelope"]))
    receipt = {
        "schema": "ep.memory-envelope-migration-preview.v1",
        "path": str(path),
        "record_count": len(rows),
        "changed_count": changed,
        "invalid_count": len(invalid),
        "invalid_samples": invalid[:20],
        "apply": apply,
        "rollback": None,
    }
    if apply and changed:
        backup = path.with_name(path.name + f".before-envelope-{int(time.time())}")
        shutil.copy2(path, backup)
        for index, envelope in updated:
            rows[index]["memory_envelope"] = envelope
        data["records"] = rows
        temporary = path.with_suffix(path.suffix + ".envelope.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        receipt["rollback"] = str(backup)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=Path.home() / ".evolving-profile/process-memory/records.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.path, apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

