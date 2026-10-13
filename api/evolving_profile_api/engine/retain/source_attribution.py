"""Deterministic author/span verification for host conversation retention.

The model selects a witness; source bytes determine its author and authority.
This module makes no semantic claim that a source quote is a confirmed fact.
"""

import hashlib
import json
import re
from typing import get_args

from pydantic import ConfigDict, Field, create_model


def requires_attribution(metadata):
    return (metadata or {}).get("source_attribution_required") == "role_quote_v1" or (metadata or {}).get(
        "source"
    ) == "codex-hook-token-batch"


def source_messages(chunk):
    try:
        messages = json.loads(chunk)
        if isinstance(messages, list) and all(isinstance(m, dict) and "role" in m for m in messages):
            return messages
    except (ValueError, TypeError):
        pass
    rows = []
    pattern = r"(?m)^(?:\[source_record: (\{[^\n]*\})\]\n)?\[role: (user|assistant)\]\n([\s\S]*?)\n\[\2:end\](?:\n|$)"
    for match in re.finditer(pattern, chunk):
        record = json.loads(match.group(1)) if match.group(1) else {}
        rows.append({"role": match.group(2), "content": match.group(3), "source_record": record})
    return rows


def validate_write_policy(chunk, metadata):
    metadata = metadata or {}
    host_source = metadata.get("source") == "codex-hook-token-batch"
    policy_version = metadata.get("retention_write_policy")
    if not host_source and policy_version != "per_turn_v1":
        return
    if policy_version != "per_turn_v1":
        raise RuntimeError("knowledge_write_policy_missing_for_legacy_host_source; scoped_recovery_required")
    messages = source_messages(chunk)
    if not messages:
        raise RuntimeError("knowledge_write_source_messages_missing")
    for message in messages:
        policy = message.get("write_policy") or {}
        if policy.get("version") != 1 or policy.get("knowledge_allowed") is not True:
            raise RuntimeError("knowledge_write_permission_missing_or_prohibited")


def attribution_schema(prompt, response_schema, metadata):
    if not requires_attribution(metadata):
        return prompt, response_schema
    base = get_args(response_schema.model_fields["facts"].annotation)[0]
    required = list((base.model_config.get("json_schema_extra") or {}).get("required", []))
    witness = create_model(
        "SourceAttributedFact",
        __base__=base,
        __config__=ConfigDict(
            json_schema_extra={"required": [*required, "source_role", "source_quote", "source_message_index"]}
        ),
        source_role=(str, Field(description="Exact original role: user or assistant. Never infer user acceptance.")),
        source_quote=(
            str,
            Field(description="Nonempty exact substring of one original message text, supporting this fact."),
        ),
        source_message_index=(int, Field(description="Zero-based index of the original message in this chunk.")),
        source_quote_ref=(str | None, Field(default=None, description="Optional exact source selector from SOURCE_QUOTE_CATALOG. If selected, source_quote must be empty or exactly its text; keep its role and message index.")),
    )
    schema = create_model("SourceAttributedResponse", facts=(list[witness], ...))
    instruction = (
        "\nSOURCE AUTHORITY: Every fact must cite source_role, source_message_index and source_quote. "
        "Use exact original message text, never nearby user prompts or assistant paraphrases. "
        "Assistant advice is an unconfirmed assistant proposal, never a user rule. "
        "Quoted or recalled old records are repetitions of their original evidence, not new user testimony. "
        "If no original source witness supports a fact, omit it. Return facts: [] when nothing qualifies. "
        "Never insert ellipses, join nonadjacent spans, or rewrite a source_quote. "
        "When a retry provides SOURCE_QUOTE_CATALOG, select its source_quote_ref and set source_quote to empty "
        "instead of retyping; its source_role and source_message_index must still match.\n"
    )
    return prompt + instruction, schema


def verbatim_witnesses(chunk, metadata):
    messages = source_messages(chunk)
    if not messages:
        raise ValueError("source_messages_missing_for_attributed_chunks")
    return [
        verify_attribution(
            chunk,
            {"source_message_index": index, "source_quote": _text(message), "source_role": message.get("role")},
            metadata,
        )
        for index, message in enumerate(messages)
        if _text(message).strip()
    ]


def _text(message):
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(b.get("text") or b.get("output_text") or "")
            for b in content
            if isinstance(b, dict) and b.get("type") not in ("tool_use", "tool_result")
        )
    return ""


QUOTE_PATTERN = r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]*"|`[^`]*`|(?m:^\s*>.*$)'


def is_source_message(message):
    return message.get("role") in ("user", "assistant") and (
        "write_policy" in message or "source_fragment" in message or "source_record" in message
    )


def _fragment_checksum(fragment):
    payload = {key: value for key, value in fragment.items() if key != "witness_sha256"}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _origin_group(record, role, original_digest):
    origin = {
        key: record[key]
        for key in ("transcript_path", "byte_offset", "raw_line_sha256", "session_id", "turn_id", "message_id")
        if record.get(key) is not None
    }
    locator = json.dumps(origin, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(f"{locator}\0{role}\0{original_digest}".encode()).hexdigest()


def _fragment_origin(message):
    text = _text(message)
    digest = hashlib.sha256(text.encode()).hexdigest()
    record = message.get("source_record") or {}
    fragment = message.get("source_fragment")
    if fragment is not None:
        if (
            not isinstance(fragment, dict)
            or fragment.get("version") != 1
            or fragment.get("role") != message.get("role")
        ):
            raise ValueError("source_original_fragment_role_invalid")
        start, end, total = (fragment.get(k) for k in ("start", "end", "original_length"))
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (start, end, total)) or not (
            0 <= start <= end <= total
        ):
            raise ValueError("source_original_fragment_span_invalid")
        if end - start != len(text) or fragment.get("content_sha256") != digest:
            raise ValueError("source_original_fragment_content_changed")
        if not fragment.get("original_content_sha256"):
            raise ValueError("source_original_fragment_witness_missing")
        if (
            fragment.get("witness_sha256") != _fragment_checksum(fragment)
            or record.get("original_message_start") != start
            or record.get("original_message_end") != end
            or record.get("original_message_length") != total
            or record.get("original_message_content_sha256") != fragment["original_content_sha256"]
        ):
            raise ValueError("source_original_fragment_witness_changed")
        if fragment.get("evidence_group_id") != _origin_group(
            record, message.get("role"), fragment["original_content_sha256"]
        ):
            raise ValueError("source_original_evidence_group_changed")
        return fragment
    start = record.get("original_message_start", 0)
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise ValueError("source_original_message_offset_invalid")
    if start and (not record.get("original_message_content_sha256") or not record.get("original_message_length")):
        raise ValueError("source_original_message_witness_missing")
    original_digest = record.get("original_message_content_sha256") or digest
    total = record.get("original_message_length", len(text))
    if isinstance(total, bool) or not isinstance(total, int) or start + len(text) > total:
        raise ValueError("source_original_message_length_invalid")
    ranges = record.get("original_message_quoted_ranges")
    if (start or total != len(text)) and ranges is None:
        raise ValueError("source_original_quote_scope_missing")
    if record.get("original_message_end", start + len(text)) != start + len(text):
        raise ValueError("source_original_message_end_invalid")
    if not start and total == len(text) and original_digest != digest:
        raise ValueError("source_original_message_content_changed")
    if ranges is None:
        ranges = [[m.start(), m.end()] for m in re.finditer(QUOTE_PATTERN, text)]
    if not isinstance(ranges, list) or any(
        not isinstance(r, list)
        or len(r) != 2
        or any(isinstance(v, bool) or not isinstance(v, int) for v in r)
        or not 0 <= r[0] <= r[1] <= total
        for r in ranges
    ):
        raise ValueError("source_original_quote_scope_invalid")
    group = _origin_group(record, message.get("role"), original_digest)
    return {
        "version": 1,
        "role": message.get("role"),
        "start": start,
        "end": start + len(text),
        "original_length": total,
        "content_sha256": digest,
        "original_content_sha256": original_digest,
        "evidence_group_id": group,
        "quoted_ranges": ranges,
    }


def fragment_source_message(message, start, end):
    """A bounded view of one original witness, preserving absolute text offsets."""
    text = _text(message)
    if not 0 <= start <= end <= len(text):
        raise ValueError("source_fragment_requested_span_invalid")
    origin = _fragment_origin(message)
    absolute_start, absolute_end = origin["start"] + start, origin["start"] + end
    content = text[start:end]
    fragment = {
        **origin,
        "start": absolute_start,
        "end": absolute_end,
        "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "quoted_ranges": [r for r in origin.get("quoted_ranges", []) if r[0] < absolute_end and absolute_start < r[1]],
    }
    fragment["witness_sha256"] = _fragment_checksum(fragment)
    record = {
        **(message.get("source_record") or {}),
        "original_message_start": absolute_start,
        "original_message_end": absolute_end,
        "original_message_length": origin["original_length"],
        "original_message_content_sha256": origin["original_content_sha256"],
    }
    return {**message, "content": content, "source_record": record, "source_fragment": fragment}


def iter_source_fragments(message, max_chars):
    """Split only source text; JSON and authority fields are independently intact."""
    text = _text(message)
    start = 0
    while start < len(text):
        low, high = start + 1, len(text)
        candidate = None
        while low <= high:
            middle = (low + high) // 2
            row = fragment_source_message(message, start, middle)
            serialized = json.dumps([row], ensure_ascii=False)
            if len(serialized) <= max_chars:
                candidate = serialized
                low = middle + 1
            else:
                high = middle - 1
        if candidate is None:
            raise ValueError("source_envelope_exceeds_chunk_budget")
        yield candidate
        start = json.loads(candidate)[0]["source_fragment"]["end"] - _fragment_origin(message)["start"]


def source_quote_catalog(chunk):
    """Bounded retry selectors bound to exact chunk bytes and author/span.

    Selectors are transport aids, not facts. Keep quotation boundaries separate
    so an old quote cannot inherit authority from adjacent user prose. Missing
    entries retain the existing exact-quote route, never fuzzy matching.
    """
    digest = hashlib.sha256(chunk.encode()).hexdigest()
    catalog = {"schema": "source-quote-catalog.v1", "chunk_sha256": digest,
               "coverage": "partial", "entries": []}
    for index, message in enumerate(source_messages(chunk)):
        if message.get("role") not in ("user", "assistant"):
            continue
        text = _text(message)
        origin = _fragment_origin(message)
        points = {0, len(text)}
        points.update(match.end() for match in re.finditer(r"\n", text))
        for lower, upper in origin.get("quoted_ranges", []):
            points.update((max(0, min(len(text), lower - origin["start"])),
                           max(0, min(len(text), upper - origin["start"]))))
        cuts = sorted(points)
        for lower, upper in zip(cuts, cuts[1:]):
            for start in range(lower, upper, 320):
                end = min(start + 320, upper)
                if not text[start:end].strip():
                    continue
                entry = {"id": f"{digest}:{index}:{start}:{end}",
                         "source_message_index": index, "source_role": message["role"],
                         "start": start, "end": end, "text": text[start:end]}
                catalog["entries"].append(entry)
                if len(catalog["entries"]) > 128 or len(json.dumps(catalog, ensure_ascii=False)) > 12000:
                    catalog["entries"].pop()
                    return catalog
    catalog["coverage"] = "full"
    return catalog


def verify_attribution(chunk, raw_fact, metadata):
    """Return canonical text/type/metadata, or reject an unproved source alias."""
    if not requires_attribution(metadata):
        return None
    messages = source_messages(chunk)
    index = raw_fact.get("source_message_index")
    quote = raw_fact.get("source_quote")
    role = raw_fact.get("source_role")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index >= len(messages):
        raise ValueError("source_message_index_missing_or_invalid")
    message = messages[index]
    text = _text(message)
    if role not in ("user", "assistant") or role != message.get("role"):
        raise ValueError("source_role_mismatch")
    selector = raw_fact.get("source_quote_ref")
    selected = None
    if selector is not None:
        if not isinstance(selector, str):
            raise ValueError("source_quote_selector_invalid")
        selected = next((e for e in source_quote_catalog(chunk)["entries"] if e["id"] == selector), None)
        if (not selected or selected["source_message_index"] != index or selected["source_role"] != role
                or quote not in ("", selected["text"])):
            raise ValueError("source_quote_selector_invalid")
        quote = selected["text"]
    if not isinstance(quote, str) or not quote.strip() or quote not in text:
        raise ValueError("source_quote_not_in_original_message")
    # A quote occurring more than once needs an unambiguous source span.
    start = selected["start"] if selected else text.find(quote)
    if text.find(quote, start + 1) >= 0:
        supplied_start = selected["start"] if selected else raw_fact.get("source_start")
        if isinstance(supplied_start, int) and text[supplied_start : supplied_start + len(quote)] == quote:
            start = supplied_start
        else:
            raise ValueError("source_quote_span_ambiguous")
    end = start + len(quote)
    origin_fragment = _fragment_origin(message)
    absolute_start, absolute_end = origin_fragment["start"] + start, origin_fragment["start"] + end
    quoted = any(
        lower <= absolute_start and absolute_end <= upper for lower, upper in origin_fragment.get("quoted_ranges", [])
    )
    source_record = message.get("source_record") or {}
    source_ids = sorted(
        set(re.findall(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", text, re.I))
    )
    repetition = quoted or message.get("statement_kind") == "source_repetition"
    if repetition:
        kind, fact_type, canonical = (
            "source_repetition",
            "experience",
            f"Source repetition (not new user testimony): {quote}",
        )
    elif role == "assistant":
        kind = (
            "assistant_proposal"
            if re.search(r"建议|可以考虑|推荐|suggest|recommend|propos", quote, re.I)
            else "assistant_statement"
        )
        fact_type, canonical = "experience", f"Assistant statement (not user-confirmed): {quote}"
    else:
        kind, fact_type, canonical = "user_statement", "world", quote
    locator = json.dumps(source_record, ensure_ascii=False, sort_keys=True)
    group = origin_fragment["evidence_group_id"]
    witness_metadata = {
        "source_role": role,
        "source_quote": quote,
        "source_message_index": str(index),
        "source_start": str(absolute_start),
        "source_end": str(absolute_end),
        "source_record": locator,
        "source_content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "original_source_content_sha256": origin_fragment["original_content_sha256"],
        "original_source_length": str(origin_fragment["original_length"]),
        "statement_kind": kind,
        "independent_user_evidence": str(kind == "user_statement").lower(),
        "evidence_group_id": group,
    }
    if source_ids:
        witness_metadata["source_memory_ids"] = ",".join(source_ids)
    if selected:
        witness_metadata["source_quote_ref"] = selector
        witness_metadata["source_quote_resolution"] = "exact_chunk_catalog_selector"
    return canonical, fact_type, witness_metadata
