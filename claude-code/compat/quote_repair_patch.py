#!/usr/bin/env python3
"""Source-quote repair for EP's fact-extraction validator (api/evolving_profile_api/engine/retain/source_attribution.py).

Problem (measured 2026-10-24): the model returns source_quote strings that are *almost* verbatim (87% >= 0.90 similarity to a
unique span of the right author's message) or are verbatim but carry the wrong source_message_index. The validator rejects
them byte-exactly, a chunk whose facts are ALL rejected fails, the retry resends the same input, and the batch is quarantined.

Fix: before the exact check, try two deterministic repairs. Both keep EP's guarantee that the stored quote is an exact
substring of the claimed author's original message:
  1. exact_quote_index_corrected - quote is verbatim in exactly one message of the claimed role, but not at the model's index
  2. snapped_to_verbatim_span    - quote is >=0.90 similar to ONE span (unique, margin >= 0.10) of a message of the claimed role;
                                   the span itself is stored instead of the model's text
Never relaxed: author/role, ambiguity (fails closed), source_quote_ref selector path, anything below the thresholds.
Provenance of a repair is recorded in the witness metadata (source_quote_resolution / source_quote_repair).
Kill switch: env EVOLVING_PROFILE_API_QUOTE_REPAIR=0 (read per call).

usage:  quote_repair_patch.py check|apply [--api DIR] [--dry-run]
"""
import argparse, os, shutil, sys, time
from pathlib import Path

DEFAULT_API = Path(os.environ.get("EP_API_SRC", "")) if os.environ.get("EP_API_SRC") else None
REL = Path("evolving_profile_api/engine/retain/source_attribution.py")

HELPERS = '''def _quote_repair_enabled():
    return os.environ.get("EVOLVING_PROFILE_API_QUOTE_REPAIR", "1").strip().lower() not in ("0", "false", "off", "no")


_QR_MIN_RATIO = 0.90
_QR_MARGIN = 0.10
_QR_MAX_QUOTE = 1500
_QR_MAX_TEXT = 80000
# `cat -n` style line numbers pasted into messages ("\\n118\\t..."): the model drops them when retyping a quote. Snapping onto such a
# span would store verbatim-but-polluted text (38 of 47 snaps in the first replay), so those stay rejected as before.
_QR_LINE_NO = re.compile(r"(?:^|\\n)[ \\t]*\\d{1,6}\\t")


def _best_verbatim_span(quote, text):
    """Closest span of `text` to `quote`: (ratio, span) or (0.0, None). Deterministic, no model, span is always a substring."""
    if len(quote) > _QR_MAX_QUOTE or len(text) > _QR_MAX_TEXT:
        return 0.0, None
    anchor = difflib.SequenceMatcher(None, quote, text, autojunk=False).find_longest_match(0, len(quote), 0, len(text))
    if anchor.size < 6:
        return 0.0, None
    pad = max(8, len(quote) // 4)
    lo = max(0, anchor.b - anchor.a - pad)
    hi = min(len(text), anchor.b - anchor.a + len(quote) + pad)
    window = text[lo:hi]
    blocks = [b for b in difflib.SequenceMatcher(None, quote, window, autojunk=False).get_matching_blocks() if b.size >= 4]
    if not blocks:
        return 0.0, None
    span = window[blocks[0].b : blocks[-1].b + blocks[-1].size].strip()
    if not span or not (0.8 <= len(span) / len(quote) <= 1.25):
        return 0.0, None
    return difflib.SequenceMatcher(None, quote, span, autojunk=False).ratio(), span


def _repair_source_quote(messages, index, role, quote):
    """None = nothing to repair or not safely repairable (caller keeps the original fail-closed behaviour);
    otherwise (index, quote, resolution). Only messages of the CLAIMED role are ever considered."""
    if not _quote_repair_enabled() or role not in ("user", "assistant"):
        return None
    if messages[index].get("role") == role and quote in _text(messages[index]):
        return None
    same = [(i, _text(m)) for i, m in enumerate(messages) if m.get("role") == role]
    exact = [i for i, t in same if quote in t]
    if len(exact) == 1:
        return exact[0], quote, {"kind": "exact_quote_index_corrected", "model_index": index}
    if exact:
        return None
    scored = []
    for i, t in same:
        ratio, span = _best_verbatim_span(quote, t)
        if span is not None and ratio >= _QR_MIN_RATIO:
            scored.append((ratio, i, span))
    scored.sort(key=lambda row: row[0], reverse=True)
    if not scored or (len(scored) > 1 and scored[0][0] - scored[1][0] < _QR_MARGIN):
        return None
    ratio, i, span = scored[0]
    if _text(messages[i]).count(span) != 1:
        return None
    if _QR_LINE_NO.search(span) and not _QR_LINE_NO.search(quote):
        return None
    return i, span, {"kind": "snapped_to_verbatim_span", "model_index": index, "similarity": round(ratio, 4),
                     "model_quote_sha256": hashlib.sha256(quote.encode()).hexdigest()}


'''

EDITS = [
    ("import hashlib\nimport json\nimport re\n", "import difflib\nimport hashlib\nimport json\nimport os\nimport re\n"),
    ("def verify_attribution(chunk, raw_fact, metadata):\n", HELPERS + "def verify_attribution(chunk, raw_fact, metadata):\n"),
    ("    message = messages[index]\n    text = _text(message)\n    if role not in",
     "    quote_repair = None\n"
     "    if raw_fact.get(\"source_quote_ref\") is None and isinstance(quote, str) and quote.strip():\n"
     "        fixed = _repair_source_quote(messages, index, role, quote)\n"
     "        if fixed is not None:\n"
     "            index, quote, quote_repair = fixed\n"
     "    message = messages[index]\n    text = _text(message)\n    if role not in"),
    ("        witness_metadata[\"source_quote_resolution\"] = \"exact_chunk_catalog_selector\"\n    return canonical, fact_type, witness_metadata",
     "        witness_metadata[\"source_quote_resolution\"] = \"exact_chunk_catalog_selector\"\n"
     "    if quote_repair:\n"
     "        witness_metadata[\"source_quote_resolution\"] = \"repaired_\" + quote_repair[\"kind\"]\n"
     "        witness_metadata[\"source_quote_repair\"] = json.dumps(quote_repair, ensure_ascii=False, sort_keys=True)\n"
     "    return canonical, fact_type, witness_metadata"),
]


def state(text):
    done = [new in text for _, new in EDITS]
    if all(done): return "applied"
    if any(done): return "partial"
    if all(old in text and text.count(old) == 1 for old, _ in EDITS): return "pristine"
    return "anchor_missing"


def apply_text(text):
    for old, new in EDITS:
        assert text.count(old) == 1, f"anchor count {text.count(old)}: {old[:60]!r}"
        text = text.replace(old, new)
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("command", choices=["check", "apply"]); ap.add_argument("--api", default=str(DEFAULT_API or ""))
    ap.add_argument("--dry-run", action="store_true"); a = ap.parse_args(argv)
    if not a.api: sys.exit("give --api <dir containing evolving_profile_api/> (or set EP_API_SRC)")
    p = Path(a.api) / REL; t = p.read_text(encoding="utf-8"); s = state(t)
    if a.command == "check":
        print(f"quote repair: {s}"); return 0 if s == "applied" else 1
    if s == "applied": print("quote repair: already applied"); return 0
    if s != "pristine": print(f"quote repair: REFUSE state={s}"); return 1
    new = apply_text(t); compile(new, str(p), "exec")
    if a.dry_run: print("quote repair: would patch"); return 0
    ts = time.strftime("%Y%m%d%H%M%S"); tmp = p.with_name(p.name + f".new-{ts}"); tmp.write_text(new, encoding="utf-8"); os.chmod(tmp, p.stat().st_mode & 0o777)
    backup = p.with_name(p.name + f".pre-quote-repair-{ts}"); shutil.copy2(p, backup); os.replace(tmp, p)
    print(f"quote repair: patched (backup {backup.name})"); return 0


if __name__ == "__main__":
    sys.exit(main())
