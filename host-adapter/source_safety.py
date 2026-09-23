"""Mask recognizable credential literals at the agent-facing source boundary.

Offsets are preserved. This is not a complete sensitive-data classifier;
source storage is unchanged and an unrecognized secret may still require review.
"""
import re

PATTERNS=[re.compile(r'\b(?:sk-(?:proj-)?|ghp_|github_pat_)[A-Za-z0-9_-]{16,}'),
    re.compile(r'(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{12,})'),
    re.compile(r'(?i)(?:api[_ -]?key|access[_ -]?token|secret|password)\s*["\']?\s*[:=]\s*["\']?([^\s"\'\\,;；}{]{8,})')]
KEY=re.compile(r'(?i)^(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|authorization|secret)$')

def mask_text(text):
    for pattern in PATTERNS:
        spans=[m.span(m.lastindex or 0) for m in pattern.finditer(text)]
        for a,b in reversed(spans):text=text[:a]+('█'*(b-a))+text[b:]
    return text

def mask_value(value):
    if isinstance(value,str):return mask_text(value)
    if isinstance(value,list):return [mask_value(v) for v in value]
    if isinstance(value,dict):return {k:('[credential redacted]' if KEY.fullmatch(str(k)) else mask_value(v)) for k,v in value.items()}
    return value
