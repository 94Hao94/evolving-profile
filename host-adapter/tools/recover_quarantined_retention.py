#!/usr/bin/env python3
"""Recover legacy retention quarantines whose source envelope was unreadable.

The command is intentionally bounded and CAS-protected:

* it only targets ``retention_retry_exhausted:failed`` groups whose current
  remote operation reports ``source_message_chain_missing``;
* it reconstructs source messages from the preserved queue bytes, adding the
  per-turn write policy required by the current API;
* it submits one replacement operation and removes the quarantine only after
  that replacement reaches ``completed`` and the queue fingerprints are
  unchanged.

Without ``--apply`` the command performs a read-only preview.  This keeps the
tool safe to run from a health check while still making the automatic repair
path explicit and auditable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from lib.client import HindsightClient
from lib.config import load_config
from lib.retention_policy import retention_turns, transcript_messages
from lib.retention_queue import RetentionQueue


def _fingerprint(row: dict) -> str:
    return hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _message_key(message: dict) -> tuple[str, str]:
    record = message.get("source_record") or {}
    source_id = record.get("raw_line_sha256") or record.get("message_id") or record.get("turn_id")
    if not source_id:
        source_id = hashlib.sha256(str(message.get("content") or "").encode()).hexdigest()
    return str(message.get("role") or "unknown"), str(source_id)


def _recovered_messages(rows: list[dict]) -> tuple[list[dict], dict]:
    messages: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in rows:
        parsed = transcript_messages(item.get("content", ""))
        if not parsed:
            raise ValueError("source_message_chain_missing")
        for message in parsed:
            text = message.get("content")
            if not isinstance(text, str) or not text.strip():
                continue
            key = _message_key(message)
            if key in seen:
                continue
            seen.add(key)
            messages.append(
                {
                    "role": message["role"],
                    "content": text,
                    "source_record": {
                        **(message.get("source_record") or {}),
                        "queue_item_id": item["id"],
                        "session_id": item.get("session_id"),
                        "project": item.get("project"),
                    },
                }
            )
    if not messages:
        raise ValueError("source_message_chain_missing")

    # Derive the same per-turn permission envelope used for new captures.
    turns = retention_turns(messages)
    for turn in turns:
        policy = dict(turn.get("write_policy") or {})
        for message in messages[turn["start"] : turn["end"]]:
            message["write_policy"] = policy
    blocked = [turn["write_policy"] for turn in turns if not turn["write_policy"].get("knowledge_allowed", True)]
    if blocked:
        raise PermissionError("knowledge_write_policy_requires_scoped_recovery")
    return messages, {"message_count": len(messages), "deduplicated": len(seen), "turn_count": len(turns)}


def _operation_status(client: HindsightClient, bank_id: str, operation_id: str) -> dict:
    return client.operation_status(bank_id, operation_id, timeout=20)


def recover_once(root: Path, *, apply: bool, wait_seconds: int = 420) -> dict:
    config = load_config()
    queue = RetentionQueue(config.get("retainQueuePath") or root / "codex/state/retention-queue.json")
    state = queue._read()
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in state["items"]:
        quarantine = row.get("retention_quarantine") or {}
        op = quarantine.get("operation_id")
        if op:
            groups.setdefault((row.get("bank_id", ""), str(op)), []).append(row)

    client = HindsightClient(config["evolvingProfileApiUrl"], config.get("evolvingProfileApiToken"))
    report = {
        "schema": "ep.retention-source-recovery.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "apply": bool(apply),
        "groups": [],
    }
    for (bank_id, original_op), rows in sorted(groups.items()):
        entry = {"bank_id": bank_id, "original_operation_id": original_op, "row_count": len(rows)}
        try:
            remote = _operation_status(client, bank_id, original_op)
            entry["remote_status"] = remote.get("status")
            entry["remote_error"] = remote.get("error_message")
            entry["failure_classification"] = (remote.get("result_metadata") or {}).get("failure_classification")
            if remote.get("status") != "failed" or (remote.get("result_metadata") or {}).get("failure_classification") != "source_message_chain_missing":
                entry["status"] = "skipped_remote_not_source_chain_missing"
                report["groups"].append(entry)
                continue
            messages, stats = _recovered_messages(rows)
            entry.update(stats)
            entry["recovery_source"] = "legacy_role_header_v2"
            entry["source_message_sha256"] = hashlib.sha256(
                json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            if not apply:
                entry["status"] = "preview_ready"
                report["groups"].append(entry)
                continue

            expected = {row["id"]: _fingerprint(row) for row in rows}
            recovery_op = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ep-retention-source-recovery-v2:{bank_id}:{original_op}"))
            item0 = rows[0]
            project = item0.get("project") or ""
            session_ids = sorted({row.get("session_id") for row in rows if row.get("session_id")})
            metadata = {
                "source": "codex-hook-token-batch",
                "project": project,
                "session_ids": ",".join(session_ids),
                "source_attribution_required": "role_quote_v1",
                "retention_write_policy": "per_turn_v1",
                "retention_item_ids": ",".join(row["id"] for row in rows),
                "source_recovery": "legacy_role_header_v2",
                "recovery_of_operation_id": original_op,
                "recovery_source_message_sha256": entry["source_message_sha256"],
            }
            payload = {
                "async": True,
                "operation_id": recovery_op,
                "items": [
                    {
                        "content": json.dumps(messages, ensure_ascii=False),
                        "document_id": "codex-source-recovery-" + recovery_op,
                        "context": config.get("retainContext", "codex"),
                        "metadata": metadata,
                        "tags": config.get("retainTags", []),
                        "observation_scopes": config.get("retainObservationScopes", "shared"),
                    }
                ],
            }
            accepted = client._request(
                "POST",
                "/v1/default/banks/" + bank_id + "/memories",
                payload,
                timeout=config.get("retainSubmitTimeout", 30),
            ).get("operation_id")
            if not accepted:
                raise RuntimeError("async_acceptance_missing")
            entry["recovery_operation_id"] = accepted
            deadline = time.time() + max(1, int(wait_seconds))
            final = {"status": "processing"}
            while time.time() < deadline:
                final = _operation_status(client, bank_id, accepted)
                if final.get("status") in {"completed", "failed", "cancelled"}:
                    break
                time.sleep(5)
            entry["recovery_remote"] = {
                "status": final.get("status"),
                "error_message": final.get("error_message"),
                "result_metadata": final.get("result_metadata"),
            }
            if final.get("status") == "completed":
                removed = queue.reconcile_quarantined_recovery(
                    bank_id,
                    original_op,
                    {"status": "completed", "operation_id": accepted},
                    expected,
                )
                entry["removed_rows"] = removed
                entry["status"] = "recovered_and_reconciled"
            else:
                entry["status"] = "recovery_operation_not_completed"
        except Exception as exc:
            entry["status"] = "recovery_error"
            entry["error"] = type(exc).__name__ + ": " + str(exc)
        report["groups"].append(entry)
    report["summary"] = {
        "group_count": len(report["groups"]),
        "recovered": sum(row.get("status") == "recovered_and_reconciled" for row in report["groups"]),
        "preview_ready": sum(row.get("status") == "preview_ready" for row in report["groups"]),
        "errors": sum(row.get("status") == "recovery_error" for row in report["groups"]),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", default="~/.evolving-profile")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=420)
    args = parser.parse_args()
    result = recover_once(Path(args.state_root).expanduser(), apply=args.apply, wait_seconds=args.wait_seconds)
    path = Path(args.state_root).expanduser() / "audit/retention-source-recovery.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

