import pytest

from lib.memory_envelope import MemoryEnvelopeError, normalize_memory_envelope, validate_memory_envelope


def test_normalizes_common_governance_fields_without_changing_content():
    value = normalize_memory_envelope({
        "kind": "fact",
        "text": "Trae host receipt observed",
        "scope": {"kind": "session", "id": "s1"},
        "audience": ["agent", "host"],
        "source_refs": [{"id": "receipt-1", "type": "native_receipt"}],
        "observed_at": "2026-11-07T12:00:00Z",
        "verification_state": "source_checked",
        "confidence": "0.8",
        "outcome": "received",
        "session_id": "s1",
    })
    assert value["schema"] == "evolving-profile.memory-envelope.v1"
    assert value["text"] == "Trae host receipt observed"
    assert value["scope"] == {"kind": "session", "id": "s1"}
    assert value["confidence"] == 0.8
    assert value["outcome"] == {"status": "received"}
    assert validate_memory_envelope(value)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("scope", {"kind": "unknown"}, "memory_envelope_scope_kind_invalid"),
        ("confidence", 1.1, "memory_envelope_confidence_out_of_range"),
        ("verification_state", "maybe", "memory_envelope_verification_state_invalid"),
        ("observed_at", "yesterday", "memory_envelope_observed_at_invalid"),
    ],
)
def test_invalid_governance_fields_fail_closed(field, value, error):
    with pytest.raises(MemoryEnvelopeError, match=error):
        normalize_memory_envelope({"kind": "fact", field: value})


def test_process_memory_rows_get_an_additive_envelope():
    from lib.process_memory import normalize_record

    value = normalize_record({
        "kind": "episode",
        "phase": "observe",
        "text": "A real host receipt was verified",
        "source_trace_ids": ["trace-1"],
        "primary_context": {"session_id": "s1", "task_id": "task-1"},
        "verification_evidence": [{"verifier_kind": "automated_test", "status": "passed"}],
        "outcome": "recovered",
    })
    assert value["memory_envelope"]["kind"] == "experience"
    assert value["memory_envelope"]["scope"] == {"kind": "task", "id": "task-1"}
    assert value["memory_envelope"]["verification_state"] == "verified"
    assert value["memory_envelope"]["source_refs"] == ["trace-1"]

