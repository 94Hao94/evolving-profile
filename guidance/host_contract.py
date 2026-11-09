"""Occurrence identity is explicit; text fingerprints never join separate turns."""
from __future__ import annotations

from hashlib import sha256
import json
import uuid


def bind_occurrence(host_event: dict, authority: dict | None = None) -> dict:
    host_event = dict(host_event or {})
    if host_event.get('host_id') not in (None,'codex'):
        # Only a caller-provided, separately authenticated entry may attest
        # this namespace. Never derive it from the event's own authority field.
        import sys
        from pathlib import Path
        adapter=str(Path(__file__).resolve().parents[1]/'host-adapter')
        if adapter not in sys.path:sys.path.insert(0,adapter)
        from lib.host_integration.identity import bind_host_identity
        bound=bind_host_identity(host_event,authority or {})
        return {**bound,'occurrence_id':host_event.get('tool_call_id') or host_event.get('message_id') or str(uuid.uuid4()),
                'prompt_sha256':sha256(str(host_event.get('prompt') or '').encode()).hexdigest()}
    occurrence_id = host_event.get("message_id") or host_event.get("tool_call_id") or str(uuid.uuid4())
    return {"occurrence_id": occurrence_id, "host_id": host_event.get("host_id"), "session_id": host_event.get("session_id"),
            "turn_id": host_event.get("turn_id"), "message_id": host_event.get("message_id"), "tool_call_id": host_event.get("tool_call_id"),
            "identity_origin": "host" if any(host_event.get(key) for key in ("turn_id", "message_id", "tool_call_id")) else "adapter_assigned",
            "prompt_sha256": sha256(str(host_event.get("prompt") or "").encode()).hexdigest()}


def join_delivery(occurrence: dict, receipts: list[dict]) -> dict | None:
    matches = [receipt for receipt in receipts if receipt.get("occurrence_id") == occurrence.get("occurrence_id")]
    return matches[-1] if matches else None
