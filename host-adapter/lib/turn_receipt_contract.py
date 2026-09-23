"""Read-only projection of one Hindsight turn across its delivery boundaries."""
from __future__ import annotations

from typing import Any, Optional


SCHEMA = "hindsight.turn_receipt_projection.v1"
DECISION_BINDING_FIELDS = (
    "session_id",
    "turn_id",
    "hook_invocation_id",
    "execution_id",
    "prompt_sha256",
    "policy_version",
    "source_revision",
)


def _text(value: Any) -> str:
    return str(value or "")


def _ingress_identity(ingress: dict[str, Any]) -> dict[str, str]:
    return {
        "session_id": _text(ingress.get("session_id")),
        "turn_id": _text(ingress.get("turn_id")),
        "hook_invocation_id": _text(
            ingress.get("hook_invocation_id") or ingress.get("invocation_id")
        ),
    }


def _decision_context(ingress: dict[str, Any]) -> dict[str, str]:
    identity = _ingress_identity(ingress)
    values = dict(ingress)
    values["hook_invocation_id"] = identity["hook_invocation_id"]
    return {field: _text(values.get(field)) for field in DECISION_BINDING_FIELDS}


def _matches_output(identity: dict[str, str], output: dict[str, Any]) -> bool:
    expected = {
        "session_id": identity["session_id"],
        "turn_id": identity["turn_id"],
        "hook_invocation_id": identity["hook_invocation_id"],
    }
    return all(expected[field] and _text(output.get(field)) == expected[field] for field in expected)


def _matches_host(identity: dict[str, str], host: dict[str, Any]) -> bool:
    return (
        bool(identity["session_id"] and identity["turn_id"])
        and _text(host.get("session_id")) == identity["session_id"]
        and _text(host.get("turn_id")) == identity["turn_id"]
    )


def _unique_texts(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _integer(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def project_turn(
    ingress: dict[str, Any], decisions: Optional[list[dict[str, Any]]],
    output: Optional[dict[str, Any]], host: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Project known facts only; missing or ambiguous evidence remains ``None``.

    ``output`` is the Hook's local receipt after stdout was flushed. ``host``
    is a native transcript receipt.  Neither is inferred from a model answer,
    a candidate count, or a nearby prompt with the same wording.
    """
    ingress = dict(ingress or {})
    identity = _ingress_identity(ingress)
    reasons: list[str] = []
    complete_identity = all(identity.values())
    if not complete_identity:
        reasons.append("ingress_identity_incomplete")

    decision_context = _decision_context(ingress)
    unique_decisions: dict[str, dict[str, Any]] = {}
    decision_binding_valid = True
    for decision in decisions or []:
        if not isinstance(decision, dict):
            reasons.append("invalid_decision_record")
            continue
        key = _text(decision.get("decision_key"))
        if not key:
            reasons.append("decision_key_missing")
            continue
        if key in unique_decisions:
            reasons.append("duplicate_decision_key")
            continue
        if decision.get("binding") != decision_context:
            reasons.append("decision_binding_mismatch")
            decision_binding_valid = False
            continue
        unique_decisions[key] = decision

    output_count: Optional[int] = None
    packed_count: Optional[int] = None
    output_ids: list[str] = []
    output_ref: dict[str, Any] = {}
    if output is None:
        reasons.append("output_receipt_missing")
    elif not isinstance(output, dict) or not _matches_output(identity, output):
        reasons.append("output_identity_mismatch")
    else:
        packet = output.get("packet_delivery")
        if not isinstance(packet, dict) or packet.get("state") != "hook_stdout_write_completed":
            reasons.append("output_delivery_unverified")
        else:
            output_count = _integer(output.get("injected_count"))
            output_ids = _unique_texts(list(output.get("injected_ids") or []))
            if output_count is None:
                reasons.append("output_count_missing")
            elif output_count != len(output_ids):
                reasons.append("output_count_id_mismatch")
            packed_count = _integer(packet.get("input_count"))
            if packed_count is None:
                packed_count = output_count
            if output_count == 0:
                reasons.append("explicit_empty_packet")
            output_ref = {
                "session_id": identity["session_id"],
                "turn_id": identity["turn_id"],
                "hook_invocation_id": identity["hook_invocation_id"],
                "context_sha256": _text(output.get("context_sha256")),
            }

    host_count: Optional[int] = None
    host_ids: list[str] = []
    host_ref: dict[str, Any] = {}
    if host is None:
        reasons.append("host_receipt_missing")
    elif not isinstance(host, dict) or not _matches_host(identity, host):
        reasons.append("host_identity_mismatch")
    else:
        host_count = _integer(host.get("visible_record_count"))
        host_ids = _unique_texts(list(host.get("visible_record_ids") or []))
        if host_count is None:
            reasons.append("host_count_missing")
        elif host_ids and host_count != len(host_ids):
            reasons.append("host_count_id_mismatch")
        if host.get("state") == "completed_without_new_memory_packet" and host_count == 0:
            reasons.append("completed_without_new_memory_packet")
        host_ref = {
            "session_id": identity["session_id"],
            "turn_id": identity["turn_id"],
            "state": _text(host.get("state")),
            "context_sha256": _text(host.get("context_sha256")),
        }

    if output_count is not None and host_count is not None:
        if output_count != host_count:
            reasons.append("host_output_count_mismatch")
        if output_ids and host_ids and set(output_ids) != set(host_ids):
            reasons.append("host_output_record_mismatch")
        elif output_ids and not host_ids and host_count:
            reasons.append("host_record_ids_unavailable")

    memory_needs = dict((output or {}).get("memory_needs") or {}) if isinstance(output, dict) else {}
    decision_rows = list(unique_decisions.values())
    decision_counts_known = decisions is not None and decision_binding_valid
    reason_codes = list(dict.fromkeys(reasons))
    return {
        "schema": SCHEMA,
        "identity": identity,
        "identity_state": "complete" if complete_identity else "incomplete",
        "facts_need": memory_needs.get("facts"),
        "guidance_need": memory_needs.get("guidance"),
        "stages": {
            "admission": {
                "decision_count": len(decision_rows) if decision_counts_known else None,
                "admit_count": sum(row.get("action") == "admit" for row in decision_rows) if decision_counts_known else None,
                "reject_count": sum(row.get("action") == "reject" for row in decision_rows) if decision_counts_known else None,
                "defer_count": sum(row.get("action") == "defer" for row in decision_rows) if decision_counts_known else None,
            },
            "packet": {"count": packed_count},
            "output": {"count": output_count, "ids": output_ids},
            "host": {"count": host_count, "ids": host_ids},
        },
        "counts": {
            "candidate": len(decision_rows) if decision_counts_known else None,
            "admitted": sum(row.get("action") == "admit" for row in decision_rows) if decision_counts_known else None,
            "packed": packed_count,
            "output": output_count,
            "host_visible": host_count,
        },
        "reason_codes": reason_codes,
        "evidence_refs": {
            "decision_keys": sorted(unique_decisions),
            "output": output_ref or None,
            "host": host_ref or None,
        },
    }


def project_trace_turn(
    trace: dict[str, Any], ingress: Optional[dict[str, Any]], host: Optional[dict[str, Any]]
) -> dict[str, Any]:
    """Adapt existing Controller/Hook trace fields without inferring delivery.

    Older trace rows can provide a candidate count but no verified decision
    records.  Those rows deliberately retain ``candidate=None`` in the new
    projection, rather than promoting a count into a contractual admission.
    """
    trace = dict(trace or {})
    source = dict(ingress or {})
    for field in ("session_id", "turn_id", "hook_invocation_id", "execution_id"):
        source.setdefault(field, trace.get(field))
    source.setdefault("prompt_sha256", source.get("prompt_fingerprint") or trace.get("user_prompt_fingerprint"))
    effect = dict(trace.get("memory_effectiveness") or {})
    source.setdefault("policy_version", effect.get("admission_policy") or trace.get("relevance_policy"))
    source.setdefault("source_revision", effect.get("source_revision") or "")
    output: Optional[dict[str, Any]] = None
    if isinstance(effect.get("packet_delivery"), dict):
        output = dict(effect)
        for field in ("session_id", "turn_id", "hook_invocation_id", "execution_id"):
            output.setdefault(field, source.get(field))
    decisions = effect.get("admission_decisions")
    if not isinstance(decisions, list):
        decisions = None
    return project_turn(source, decisions, output, host)
