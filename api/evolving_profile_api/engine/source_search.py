"""Literal source-span matching for provenance checks."""
from __future__ import annotations

import hashlib
import re


_ROLE_SPAN = re.compile(
    r"\[role:\s*(user|assistant|tool|system|developer)\]\s*(.*?)\s*\[(?:user|assistant|tool|system|developer):end\]",
    re.I | re.S,
)


def literal_source_matches(
    text: str,
    *,
    terms: list[str],
    match: str,
    role: str,
    document_id: str,
    chunk_id: str,
) -> list[dict]:
    source = str(text or "")
    needles = [str(value).strip() for value in terms if str(value).strip()]
    if not source or not needles:
        return []
    spans = []
    for found in _ROLE_SPAN.finditer(source):
        spans.append((found.group(1).casefold(), found.start(2), found.end(2), found.group(2)))
    if role == "any":
        candidates = spans or [("unknown", 0, len(source), source)]
    else:
        candidates = [value for value in spans if value[0] == role]
    result = []
    for format_role, start, end, body in candidates:
        hits = [needle.casefold() in body.casefold() for needle in needles]
        if not (all(hits) if match == "all" else any(hits)):
            continue
        positions = [body.casefold().find(needle.casefold()) for needle in needles]
        positions = [value for value in positions if value >= 0]
        anchor = min(positions) if positions else 0
        local_start = max(0, anchor - 700)
        local_end = min(len(body), max(anchor + max(map(len, needles)) + 700, local_start + 1))
        result.append({
            "document_id": document_id,
            "chunk_id": chunk_id,
            "span_start": start + local_start,
            "span_end": start + local_end,
            "text": body[local_start:local_end],
            "format_role": format_role,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "anchor_memory_id": None,
        })
    return result
