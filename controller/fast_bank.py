#!/usr/bin/env python3
"""Read-only, latency-bounded recall cache for the Hindsight controller.

This is deliberately a *derived cache*, not a second memory bank.  It is
rebuilt from a Hindsight export and explicit candidate/policy overlays. Every row
still goes through the controller's normal relevance, time and source
governance before it can reach a Memory Packet.  Its only job is to keep an
interactive Hook from becoming a zero-memory turn when the official Recall
endpoint is busy with a long vector/LLM operation.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


STATE_ROOT = Path(os.environ.get("EVOLVING_PROFILE_STATE_ROOT", str(Path.home() / ".evolving-profile")))
DEFAULT_SNAPSHOT = STATE_ROOT / "backups/v2-cutover-20260812T191145/personal-memory.memory_units.jsonl"
DEFAULT_INDEX = STATE_ROOT / "control-plane/fast-memory-index.sqlite3"
DEFAULT_COMMON = STATE_ROOT / "common-candidates.json"
DEFAULT_POLICIES = STATE_ROOT / "directive-policy-index.json"
DEFAULT_TRACE_INDEX = STATE_ROOT / "control-plane/recall-trace-index.json"
# Schema 4 removes retrieval-output feedback as a memory source. Runtime
# reconciliation tracks withdrawals and all record fields, not just text.
INDEX_SCHEMA = 4
RUNTIME_REFRESH_INTERVAL_SECONDS = 3.0


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _text(row: dict[str, Any]) -> str:
    return str(row.get("text") or row.get("content") or "").strip()


def _row_id(row: dict[str, Any], prefix: str = "") -> str:
    value = str(row.get("id") or row.get("chunk_id") or row.get("source_memory_id") or row.get("candidate_id") or "").strip()
    if not value:
        return ""
    return (prefix + value)[:240]


def _normalise_record(row: dict[str, Any], *, source: str, prefix: str = "") -> dict[str, Any] | None:
    text = _text(row)
    identifier = _row_id(row, prefix)
    if not text or not identifier:
        return None
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if not metadata:
        metadata = {}
    # Preserve the authoritative source label when the export has one.  The
    # cache marker is additive and is intentionally ignored by source/time
    # governance.
    metadata = dict(metadata)
    metadata.setdefault("_ccy_fast_bank", {})
    metadata["_ccy_fast_bank"].update({
        "source": source,
        "derived_cache": True,
        "schema": INDEX_SCHEMA,
    })
    fact_type = str(row.get("type") or row.get("fact_type") or "world").strip() or "world"
    score = row.get("score")
    if score is None and isinstance(row.get("scores"), dict):
        score = row["scores"].get("final")
    return {
        "id": identifier,
        "text": text[:12000],
        "type": fact_type,
        "context": str(row.get("context") or ""),
        "document_id": str(row.get("document_id") or row.get("source_document_id") or ""),
        "event_date": str(row.get("event_date") or ""),
        "occurred_start": str(row.get("occurred_start") or ""),
        "occurred_end": str(row.get("occurred_end") or ""),
        "mentioned_at": str(row.get("mentioned_at") or row.get("event_time") or ""),
        "metadata": metadata,
        "tags": list(row.get("tags") or []) if isinstance(row.get("tags"), list) else [],
        "base_score": float(score or 0.0),
    }


def _iter_snapshot(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(row, dict):
                yield row


def _iter_supplemental(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    rows = payload.get("candidates") if isinstance(payload, dict) else payload
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            # ``common-candidates.json`` is an append-only queue.  Its
            # superseded, retired and explicitly discarded records are not a
            # fallback memory source.  Older test fixtures do not carry these
            # lifecycle fields, so absence remains backward-compatible.
            status = str(row.get("status") or "").strip().casefold()
            decision = str(row.get("decision") or "").strip().casefold()
            if status or decision:
                if status and status not in {"processed", "active", "active_provisional"}:
                    continue
                if decision and decision not in {"add", "accepted", "accept", "qualified", "keep"}:
                    continue
            yield row


def _iter_policies(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    rows = payload.get("policies") if isinstance(payload, dict) else []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or row.get("status") not in {None, "active", "active_provisional"}:
                continue
            text = str(row.get("policy") or row.get("original_text") or "").strip()
            if text:
                yield {
                    "id": f"direct-policy:{row.get('source_memory_id') or row.get('policy_id') or ''}",
                    "text": text,
                    "type": "direct_policy",
                    "metadata": {
                        "source_class": "direct_policy",
                        "policy_status": row.get("status") or "active_provisional",
                        "policy_id": row.get("policy_id"),
                        "source_memory_id": row.get("source_memory_id"),
                        "direct_policy_scope": row.get("scope"),
                        "direct_policy_boundary": row.get("boundary"),
                        "direct_policy_keywords": row.get("keywords") or [],
                    },
                    "tags": row.get("keywords") or [],
                }


def _iter_trace_items(path: Path, *, max_entries: int = 1800) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    entries = payload.get("entries") if isinstance(payload, dict) else {}
    if not isinstance(entries, dict):
        return
    values = sorted(
        (value for value in entries.values() if isinstance(value, dict)),
        key=lambda row: str(row.get("at") or ""), reverse=True,
    )[:max_entries]
    for entry in values:
        for item in list(entry.get("selected_results") or []) + list(entry.get("injected_items") or []):
            if isinstance(item, dict) and _text(item):
                yield item


class FastMemoryBank:
    """Small local lexical index used only as an official-recall timeout lane."""

    def __init__(
        self,
        snapshot_path: Path = DEFAULT_SNAPSHOT,
        index_path: Path = DEFAULT_INDEX,
        *,
        trace_index_path: Path = DEFAULT_TRACE_INDEX,
        common_path: Path = DEFAULT_COMMON,
        policies_path: Path = DEFAULT_POLICIES,
    ) -> None:
        self.snapshot_path = Path(snapshot_path).expanduser()
        self.index_path = Path(index_path).expanduser()
        self.trace_index_path = Path(trace_index_path).expanduser()
        self.common_path = Path(common_path).expanduser()
        self.policies_path = Path(policies_path).expanduser()
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._ready = False
        self._load_error = ""
        self._built_at = ""
        self._runtime_signature: dict[str, Any] = {}
        self._runtime_refreshed_at = ""
        self._last_runtime_check = 0.0
        self._runtime_refresh_error = ""

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def load_error(self) -> str:
        return self._load_error

    def _signature(self) -> dict[str, Any]:
        try:
            stat = self.snapshot_path.stat()
            return {"path": str(self.snapshot_path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        except OSError:
            return {"path": str(self.snapshot_path), "bytes": 0, "mtime_ns": 0}

    @staticmethod
    def _file_signature(path: Path) -> dict[str, Any]:
        try:
            stat = path.stat()
            return {"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        except OSError:
            return {"path": str(path), "bytes": 0, "mtime_ns": 0}

    def _runtime_source_signature(self) -> dict[str, Any]:
        """Return cheap mtime/size stamps for sources that grow at runtime.

        The derived cache must not become a second authoritative store.  A
        source stamp is therefore sufficient for deciding whether to refresh;
        candidate/policy projections are parsed only after the stamp changes.
        """
        return {
            "common_candidates": self._file_signature(self.common_path),
            "direct_policies": self._file_signature(self.policies_path),
        }

    def ensure_ready(self) -> bool:
        with self._lock:
            if self._ready and self._conn is not None:
                stored = self._conn.execute("SELECT value FROM fast_meta WHERE key='signature'").fetchone()
                if not self.snapshot_path.is_file():
                    self._runtime_refresh_error = 'canonical_snapshot_unavailable_using_last_good_cache'
                    return True
                if stored and json.loads(stored[0]) == self._signature():
                    self._refresh_runtime_if_needed()
                    return True
                self._conn.close()
                self._conn = None
                self._ready = False
            try:
                self.index_path.parent.mkdir(parents=True, exist_ok=True)
                signature = self._signature()
                fresh = False
                if self.index_path.exists():
                    try:
                        probe = sqlite3.connect(f"file:{self.index_path}?mode=ro", uri=True, timeout=0.5)
                        row = probe.execute("SELECT value FROM fast_meta WHERE key='signature'").fetchone()
                        schema = probe.execute("SELECT value FROM fast_meta WHERE key='schema'").fetchone()
                        fresh = bool(row and json.loads(row[0]) == signature and schema and int(schema[0]) == INDEX_SCHEMA)
                        probe.close()
                    except Exception:
                        fresh = False
                if not fresh:
                    self._build(signature)
                self._conn = sqlite3.connect(str(self.index_path), check_same_thread=False, timeout=1.5)
                self._conn.row_factory = sqlite3.Row
                # The derived index is a read-only acceleration lane. Keep its
                # per-process SQLite cache bounded; the default cache plus the
                # trigram FTS tables otherwise leaves hundreds of MB resident
                # after a large first build even though the index is only ~32MB.
                self._conn.execute("PRAGMA mmap_size=0")
                self._conn.execute("PRAGMA cache_size=-8192")
                self._conn.execute("PRAGMA temp_store=FILE")
                self._ready = True
                self._load_error = ""
                meta = self._conn.execute("SELECT value FROM fast_meta WHERE key='built_at'").fetchone()
                self._built_at = str(meta[0]) if meta else ""
                runtime_meta = self._conn.execute("SELECT value FROM fast_meta WHERE key='runtime_signature'").fetchone()
                try:
                    self._runtime_signature = json.loads(str(runtime_meta[0])) if runtime_meta else {}
                except (TypeError, ValueError):
                    self._runtime_signature = {}
                refreshed_meta = self._conn.execute("SELECT value FROM fast_meta WHERE key='runtime_refreshed_at'").fetchone()
                self._runtime_refreshed_at = str(refreshed_meta[0]) if refreshed_meta else ""
                self._last_runtime_check = 0.0
                self._refresh_runtime_if_needed(force=True)
                return True
            except Exception as error:  # pragma: no cover - defensive production path
                self._load_error = repr(error)
                self._ready = False
                return False

    def _build(self, signature: dict[str, Any]) -> None:
        tmp = self.index_path.with_suffix(self.index_path.suffix + f".tmp-{os.getpid()}-{int(time.time())}")
        try:
            conn = sqlite3.connect(str(tmp), timeout=30)
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=OFF")
            conn.execute("CREATE TABLE memory_units (rowid INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, text TEXT NOT NULL, type TEXT, context TEXT, document_id TEXT, event_date TEXT, occurred_start TEXT, occurred_end TEXT, mentioned_at TEXT, metadata_json TEXT, tags_json TEXT, base_score REAL NOT NULL DEFAULT 0)")
            conn.execute("CREATE VIRTUAL TABLE memory_fts USING fts5(text, content='memory_units', content_rowid='rowid', tokenize='trigram')")
            conn.execute("CREATE TABLE fast_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            rows: dict[str, dict[str, Any]] = {}
            for row in _iter_snapshot(self.snapshot_path):
                item = _normalise_record(row, source="v2_memory_units_snapshot")
                if item:
                    rows.setdefault(item["id"], item)
            for row in _iter_supplemental(self.common_path):
                item = _normalise_record(row, source="common_candidates", prefix="candidate:")
                if item:
                    rows.setdefault(item["id"], item)
            for row in _iter_policies(self.policies_path):
                item = _normalise_record(row, source="direct_policy_index")
                if item:
                    rows.setdefault(item["id"], item)
            # Prior retrieval decisions are audit events, never new memories.
            insert_sql = "INSERT INTO memory_units (id,text,type,context,document_id,event_date,occurred_start,occurred_end,mentioned_at,metadata_json,tags_json,base_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            inserted = 0
            for item in rows.values():
                try:
                    cur = conn.execute(insert_sql, (
                        item["id"], item["text"], item["type"], item["context"], item["document_id"],
                        item["event_date"], item["occurred_start"], item["occurred_end"], item["mentioned_at"],
                        json.dumps(item["metadata"], ensure_ascii=False, separators=(",", ":")),
                        json.dumps(item["tags"], ensure_ascii=False, separators=(",", ":")), item["base_score"],
                    ))
                    conn.execute("INSERT INTO memory_fts(rowid,text) VALUES (?,?)", (cur.lastrowid, item["text"]))
                    inserted += 1
                except sqlite3.IntegrityError:
                    continue
            conn.execute("INSERT INTO fast_meta(key,value) VALUES('schema',?)", (str(INDEX_SCHEMA),))
            conn.execute("INSERT INTO fast_meta(key,value) VALUES('signature',?)", (json.dumps(signature, sort_keys=True),))
            conn.execute("INSERT INTO fast_meta(key,value) VALUES('built_at',?)", (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),))
            conn.execute("INSERT INTO fast_meta(key,value) VALUES('row_count',?)", (str(inserted),))
            conn.execute("INSERT INTO fast_meta(key,value) VALUES('runtime_signature',?)", (json.dumps(self._runtime_source_signature(), sort_keys=True),))
            conn.execute("INSERT INTO fast_meta(key,value) VALUES('runtime_refreshed_at',?)", (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),))
            conn.execute("INSERT INTO fast_meta(key,value) VALUES('runtime_row_count',?)", (str(sum(1 for key in rows if key.startswith(('candidate:', 'direct-policy:')))),))
            conn.commit()
            conn.close()
            os.replace(tmp, self.index_path)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass

    def _refresh_runtime_if_needed(self, *, force: bool = False) -> None:
        """Reconcile explicit overlays; retrieval traces are never sources."""
        if not self._conn:
            return
        now = time.monotonic()
        signature = self._runtime_source_signature()
        # Stat calls are cheap compared with parsing; check the stamp on every
        # search so a just-written trace is visible immediately.  The interval
        # only throttles reparsing when the stamp is unchanged.
        if not force and signature == self._runtime_signature:
            self._last_runtime_check = now
            return
        self._last_runtime_check = now

        # A trace index is atomically replaced by the Controller, but a
        # partially written/invalid JSON should never erase the last good
        # derived rows.  Parse it before mutating SQLite and leave the old
        # signature intact when parsing fails.
        try:
            # A missing/corrupt file is not an authoritative empty collection.
            for path, key in ((self.common_path, 'candidates'), (self.policies_path, 'policies')):
                payload = json.loads(path.read_text(encoding='utf-8'))
                rows = payload.get(key) if isinstance(payload, dict) else payload
                if not isinstance(rows, list):
                    raise ValueError(f'invalid {key} collection')
            common_rows = list(_iter_supplemental(self.common_path))
            policy_rows = list(_iter_policies(self.policies_path))
        except Exception as error:  # pragma: no cover - defensive production path
            self._runtime_refresh_error = repr(error)
            return

        normalised: dict[str, dict[str, Any]] = {}
        active_common_ids: set[str] = set()
        for row in common_rows:
            item = _normalise_record(row, source="common_candidates", prefix="candidate:")
            if item:
                normalised[item["id"]] = item
                active_common_ids.add(item["id"])
        for row in policy_rows:
            item = _normalise_record(row, source="direct_policy_index")
            if item:
                normalised[item["id"]] = item
                active_common_ids.add(item["id"])

        insert_sql = "INSERT INTO memory_units (id,text,type,context,document_id,event_date,occurred_start,occurred_end,mentioned_at,metadata_json,tags_json,base_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
        try:
            changed = 0
            # Remove rows that disappeared from the active common-candidate
            # projection (for example a record newly marked discarded or
            # superseded).  Without this cleanup the old index kept returning
            # stale candidate wrappers indefinitely after every refresh.
            existing_common = self._conn.execute(
                "SELECT rowid,id FROM memory_units WHERE id LIKE 'candidate:%' OR id LIKE 'direct-policy:%' OR id LIKE 'trace:%'"
            ).fetchall()
            for existing in existing_common:
                existing_id = str(existing[1] or "")
                if existing_id in active_common_ids:
                    continue
                rowid = int(existing[0])
                self._conn.execute("DELETE FROM memory_fts WHERE rowid=?", (rowid,))
                self._conn.execute("DELETE FROM memory_units WHERE rowid=?", (rowid,))
                changed += 1
            for item in normalised.values():
                existing = self._conn.execute("SELECT rowid,id,text,type,context,document_id,event_date,occurred_start,occurred_end,mentioned_at,metadata_json,tags_json,base_score FROM memory_units WHERE id=?", (item["id"],)).fetchone()
                values = (
                    item["id"], item["text"], item["type"], item["context"], item["document_id"],
                    item["event_date"], item["occurred_start"], item["occurred_end"], item["mentioned_at"],
                    json.dumps(item["metadata"], ensure_ascii=False, separators=(",", ":")),
                    json.dumps(item["tags"], ensure_ascii=False, separators=(",", ":")), item["base_score"],
                )
                if existing and tuple(existing)[1:] == values:
                    continue
                if existing:
                    rowid = int(existing[0])
                    self._conn.execute("DELETE FROM memory_fts WHERE rowid=?", (rowid,))
                    self._conn.execute(
                        "UPDATE memory_units SET text=?,type=?,context=?,document_id=?,event_date=?,occurred_start=?,occurred_end=?,mentioned_at=?,metadata_json=?,tags_json=?,base_score=? WHERE rowid=?",
                        (item["text"], item["type"], item["context"], item["document_id"], item["event_date"], item["occurred_start"], item["occurred_end"], item["mentioned_at"], values[9], values[10], item["base_score"], rowid),
                    )
                else:
                    rowid = int(self._conn.execute(insert_sql, values).lastrowid)
                self._conn.execute("INSERT INTO memory_fts(rowid,text) VALUES (?,?)", (rowid, item["text"]))
                changed += 1
            self._conn.execute("INSERT OR REPLACE INTO fast_meta(key,value) VALUES('runtime_signature',?)", (json.dumps(signature, sort_keys=True),))
            refreshed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._conn.execute("INSERT OR REPLACE INTO fast_meta(key,value) VALUES('runtime_refreshed_at',?)", (refreshed_at,))
            self._conn.execute("INSERT OR REPLACE INTO fast_meta(key,value) VALUES('runtime_row_count',?)", (str(len(normalised)),))
            self._conn.commit()
            self._runtime_signature = signature
            self._runtime_refreshed_at = refreshed_at
            self._runtime_refresh_error = ""
        except Exception as error:  # pragma: no cover - defensive production path
            self._runtime_refresh_error = repr(error)
            try:
                self._conn.rollback()
            except Exception:
                pass

    @staticmethod
    def _terms(query: str) -> list[str]:
        compact = _compact(query)
        terms: list[str] = []
        # Keep distinctive ASCII identifiers whole; they are much more useful
        # than a sea of single-character Chinese matches.
        # Do not remove spaces before extracting ASCII tokens.  The previous
        # ``_compact`` call joined ``"runtime refresh marker"`` into one
        # impossible token, so fast recovery silently returned zero for
        # English/mixed Full Prompts even when the index contained all three
        # words.
        ascii_query = re.sub(r"\s+", " ", str(query or "")).casefold()
        terms.extend(token for token in re.findall(r"[a-z][a-z0-9_.:/-]{2,}", ascii_query) if token not in {"the", "and", "for"})
        cjk = "".join(re.findall(r"[\u3400-\u9fff]", compact))
        for width in (3, 2):
            for index in range(max(0, len(cjk) - width + 1)):
                term = cjk[index:index + width]
                if term not in terms:
                    terms.append(term)
        # Queries with no CJK/ASCII run are not meaningful recall requests.
        return terms[:36]

    def search(self, query: str, *, limit: int = 96, types: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.monotonic()
        if not self.ensure_ready() or self._conn is None:
            return [], {"enabled": True, "status": "failed", "error": self._load_error, "candidate_count": 0, "selected_count": 0}
        terms = self._terms(query)
        receipt: dict[str, Any] = {
            "enabled": True,
            "status": "completed",
            "endpoint": "local_fast_bank_cache",
            "cache_path": str(self.index_path),
            "snapshot_path": str(self.snapshot_path),
            "cache_as_of": self._built_at,
            "runtime_cache_as_of": self._runtime_refreshed_at or None,
            "runtime_source_signature": self._runtime_signature,
            "query_terms": terms[:16],
            "candidate_count": 0,
            "selected_count": 0,
            "stale_source_warning": True,
            "runtime_refresh_error": self._runtime_refresh_error or None,
            "cache_consistency": "dated_snapshot_plus_explicit_overlays_not_live_bank",
            "reason": "官方 Recall 未完成时使用的只读导出缓存；仅同步规范快照与 candidate/policy 投影，不从检索结果回灌知识。并非实时完整 Bank，不能据缓存零结果断言没有记忆。",
        }
        if not terms:
            receipt["status"] = "skipped"
            receipt["reason"] = "当前 Full Prompt 没有可检索的稳定词面锚点。"
            return [], receipt
        allowed_types = {str(value) for value in (types or []) if str(value)}
        # FTS5 trigram treats each quoted term as a literal trigram. OR keeps
        # candidate generation broad; Python scoring below requires multiple
        # independent hits before a row can enter the Controller.
        match_terms = [term for term in terms if len(term) >= 3]
        if not match_terms:
            return [], receipt
        match = " OR ".join('"' + term.replace('"', "") + '"' for term in match_terms[:28])
        try:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT m.*, bm25(memory_fts) AS rank FROM memory_fts JOIN memory_units m ON m.rowid=memory_fts.rowid WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
                    (match, max(200, min(1200, int(limit) * 8))),
                ).fetchall()
        except Exception as error:
            receipt.update({"status": "failed", "error": repr(error)})
            return [], receipt
        scored: list[tuple[float, sqlite3.Row, int, float]] = []
        compact_query = _compact(query)
        for row in rows:
            if allowed_types and str(row["type"] or "") not in allowed_types:
                continue
            compact_text = _compact(row["text"])
            hits = sum(1 for term in terms if term in compact_text)
            if hits < 2:
                continue
            coverage = hits / max(2.0, min(12.0, float(len(terms))))
            exact = 1.0 if len(compact_query) >= 8 and compact_query in compact_text else 0.0
            # bm25 is negative in SQLite; lower (more negative) is better.
            rank = float(row["rank"] or 0.0)
            lexical_score = min(1.0, 0.34 + 0.055 * hits + 0.40 * coverage + 0.16 * exact + min(0.12, max(0.0, -rank) / 100.0))
            scored.append((lexical_score, row, hits, coverage))
        scored.sort(key=lambda item: (item[0], item[3], item[2], str(item[1]["mentioned_at"] or item[1]["event_date"] or "")), reverse=True)
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for score, row, hits, coverage in scored[: max(1, int(limit))]:
            identifier = str(row["id"] or "")
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            try:
                metadata = json.loads(str(row["metadata_json"] or "{}"))
            except ValueError:
                metadata = {}
            metadata = dict(metadata) if isinstance(metadata, dict) else {}
            fast_meta = dict(metadata.get("_ccy_fast_bank") or {})
            fast_meta.update({"lexical_score": round(score, 6), "term_hits": hits, "term_coverage": round(coverage, 6)})
            metadata["_ccy_fast_bank"] = fast_meta
            try:
                tags = json.loads(str(row["tags_json"] or "[]"))
            except ValueError:
                tags = []
            selected.append({
                "id": identifier,
                "text": str(row["text"] or ""),
                "type": str(row["type"] or "world"),
                "context": str(row["context"] or ""),
                "document_id": str(row["document_id"] or ""),
                "event_date": str(row["event_date"] or ""),
                "occurred_start": str(row["occurred_start"] or ""),
                "occurred_end": str(row["occurred_end"] or ""),
                "mentioned_at": str(row["mentioned_at"] or ""),
                "metadata": metadata,
                "tags": tags if isinstance(tags, list) else [],
                "scores": {"final": round(score, 6), "keyword": round(coverage, 6), "semantic": None},
            })
        receipt["candidate_count"] = len(rows)
        receipt["selected_count"] = len(selected)
        receipt["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
        return selected, receipt


__all__ = ["FastMemoryBank", "DEFAULT_SNAPSHOT", "DEFAULT_INDEX"]
