"""Small control registry. Hindsight remains the source of knowledge and source text."""
from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time
import uuid


class GuidanceRepository:
    def __init__(self, path: str | Path, bank_id: str):
        self.path, self.bank_id = Path(path), bank_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()
        if self._meta("bank_id") is None:
            self._set_meta("bank_id", bank_id)
            self._set_meta("active_revision", "")
            self._set_meta("owner_token", "owner-a")
        elif self._meta("bank_id") != bank_id:
            raise ValueError("repository_bank_mismatch")

    def _conn(self):
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def _create_schema(self):
        with self._conn() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS publications (
              id TEXT PRIMARY KEY, state TEXT NOT NULL, proposal_json TEXT NOT NULL, review_json TEXT NOT NULL,
              proposal_sha256 TEXT NOT NULL, expected_active_revision TEXT NOT NULL, source_tokens_json TEXT NOT NULL,
              owner_token TEXT NOT NULL, unit_id TEXT, created_at REAL NOT NULL, activated_at REAL, failure_code TEXT);
            CREATE TABLE IF NOT EXISTS unit_revisions (
              unit_id TEXT NOT NULL, revision TEXT NOT NULL, publication_id TEXT NOT NULL, payload_json TEXT NOT NULL,
              active INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, PRIMARY KEY(unit_id, revision));
            CREATE TABLE IF NOT EXISTS source_tokens (memory_id TEXT PRIMARY KEY, revision TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL, payload_json TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS model_revisions (model_id TEXT NOT NULL, revision TEXT NOT NULL, payload_json TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, PRIMARY KEY(model_id,revision));
            CREATE TABLE IF NOT EXISTS unit_audits (
              unit_id TEXT NOT NULL, revision TEXT NOT NULL, state TEXT NOT NULL, scope_level TEXT NOT NULL,
              validity_kind TEXT NOT NULL, reason TEXT NOT NULL, checked_at REAL NOT NULL,
              superseded_by TEXT, audit_json TEXT NOT NULL, PRIMARY KEY(unit_id,revision));
            CREATE TABLE IF NOT EXISTS idempotency (key TEXT NOT NULL, operation TEXT NOT NULL, result_json TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(key,operation));
            """)

    def _meta(self, key: str) -> str | None:
        with self._conn() as db:
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str, db=None):
        target = db or self._conn()
        target.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        if db is None:
            target.close()

    @contextmanager
    def transaction(self):
        with self._conn() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except Exception:
                db.execute("ROLLBACK")
                raise
            else:
                db.execute("COMMIT")

    def active_revision(self) -> str | None:
        return self._meta("active_revision") or None

    def owner_token(self) -> str:
        return self._meta("owner_token") or ""

    def set_owner(self, token: str):
        if not token:
            raise ValueError("empty_owner_token")
        self._set_meta("owner_token", token)

    def set_source_token(self, memory_id: str, revision: str):
        with self._conn() as db:
            db.execute("INSERT INTO source_tokens(memory_id,revision) VALUES(?,?) ON CONFLICT(memory_id) DO UPDATE SET revision=excluded.revision", (memory_id, revision))

    def prepare(self, proposal: dict, review: dict, proposal_sha256: str, owner_token: str) -> dict:
        publication_id = str(uuid.uuid4())
        unit_id = proposal.get("target_id") or "guidance:" + sha256(proposal_sha256.encode()).hexdigest()[:24]
        source_tokens = {str(ref.get("memory_id")): str(ref["source_revision"]) for ref in proposal["evidence_refs"] if ref.get("memory_id")}
        with self.transaction() as db:
            for memory_id, revision in source_tokens.items():
                db.execute("INSERT OR IGNORE INTO source_tokens(memory_id,revision) VALUES(?,?)", (memory_id, revision))
            db.execute("INSERT INTO publications VALUES(?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
                       (publication_id, "verified", json.dumps(proposal, ensure_ascii=False), json.dumps(review, ensure_ascii=False),
                        proposal_sha256, self.active_revision() or "", json.dumps(source_tokens, sort_keys=True), owner_token, unit_id, time.time()))
        return {"publication_id": publication_id, "unit_id": unit_id, "source_tokens": source_tokens,
                "expected_active_revision": self.active_revision()}

    def publication(self, publication_id: str) -> dict:
        with self._conn() as db:
            row = db.execute("SELECT * FROM publications WHERE id=?", (publication_id,)).fetchone()
        if not row:
            raise KeyError("publication_not_found")
        value = dict(row)
        for key in ("proposal_json", "review_json", "source_tokens_json"):
            value[key[:-5]] = json.loads(value.pop(key))
        return value

    def current_source_tokens(self, tokens: dict) -> dict:
        if not tokens:
            return {}
        with self._conn() as db:
            rows = db.execute("SELECT memory_id,revision FROM source_tokens WHERE memory_id IN (%s)" % ",".join("?" * len(tokens)), tuple(tokens)).fetchall()
        return {row["memory_id"]: row["revision"] for row in rows}

    def activate(self, publication_id: str, expected_active_revision: str | None, source_tokens: dict, owner_token: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM publications WHERE id=?", (publication_id,)).fetchone()
            if not row:
                raise KeyError("publication_not_found")
            if row["state"] == "active":
                return {"state": "active", "publication_id": publication_id, "revision": self.active_revision()}
            if row["state"] != "verified":
                raise ValueError("publication_not_ready")
            if self._meta("owner_token") != owner_token or row["owner_token"] != owner_token:
                raise PermissionError("owner_conflict")
            current = self._meta("active_revision") or ""
            if current != (expected_active_revision or "") or row["expected_active_revision"] != (expected_active_revision or ""):
                raise RuntimeError("revision_conflict")
            if json.loads(row["source_tokens_json"]) != source_tokens or self.current_source_tokens(source_tokens) != source_tokens:
                raise RuntimeError("revision_conflict")
            payload = json.loads(row["proposal_json"])
            revision = "sha256:" + sha256((row["proposal_sha256"] + publication_id).encode()).hexdigest()
            db.execute("UPDATE unit_revisions SET active=0 WHERE unit_id=?", (row["unit_id"],))
            db.execute("INSERT INTO unit_revisions(unit_id,revision,publication_id,payload_json,active,created_at) VALUES(?,?,?,?,1,?)",
                       (row["unit_id"], revision, publication_id, json.dumps(payload, ensure_ascii=False), time.time()))
            db.execute("UPDATE publications SET state='active', activated_at=? WHERE id=?", (time.time(), publication_id))
            self._set_meta("active_revision", revision, db)
        return {"state": "active", "publication_id": publication_id, "revision": revision, "unit_id": row["unit_id"]}

    def active_units(self) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT unit_id,revision,publication_id,payload_json,created_at FROM unit_revisions WHERE active=1 ORDER BY created_at").fetchall()
        result = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload.update(id=row["unit_id"], revision=row["revision"], publication_id=row["publication_id"], status="active", activated_at=row["created_at"])
            result.append(payload)
        if not result:
            return result
        with self._conn() as db:
            audit_rows = db.execute("SELECT * FROM unit_audits WHERE (unit_id,revision) IN (%s)" % ",".join("(?,?)" for _ in result),
                                    tuple(value for unit in result for value in (unit["id"], unit["revision"]))).fetchall()
        audits = {(row["unit_id"], row["revision"]): {**dict(row), "audit": json.loads(row["audit_json"])} for row in audit_rows}
        for unit in result:
            unit["preference_audit"] = audits.get((unit["id"], unit["revision"]), {"state": "not_reviewed", "scope_level": "unknown", "validity_kind": "unknown", "reason": "audit_required"})
        return result

    def set_unit_audit(self, unit_id: str, revision: str, audit: dict):
        allowed = {"approved", "restricted", "needs_review", "superseded", "stale"}
        if audit.get("state") not in allowed:
            raise ValueError("invalid_unit_audit_state")
        with self._conn() as db:
            db.execute("INSERT INTO unit_audits VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(unit_id,revision) DO UPDATE SET state=excluded.state,scope_level=excluded.scope_level,validity_kind=excluded.validity_kind,reason=excluded.reason,checked_at=excluded.checked_at,superseded_by=excluded.superseded_by,audit_json=excluded.audit_json",
                       (unit_id, revision, audit["state"], audit.get("scope_level", "domain"), audit.get("validity_kind", "context_sensitive"), audit.get("reason", ""), time.time(), audit.get("superseded_by"), json.dumps(audit, ensure_ascii=False)))

    def mark_unit_superseded(self, unit_id: str, revision: str, *, superseded_by: str, reason: str,
                             authority: str = "current_user_prompt_or_current_authoritative_state") -> dict:
        """Retire a preference from selection without deleting its history/source."""
        if not superseded_by or not reason:
            raise ValueError("supersession_reason_required")
        audit = {
            "state": "superseded", "scope_level": "domain", "validity_kind": "superseded",
            "reason": reason, "superseded_by": superseded_by, "authority": authority,
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        self.set_unit_audit(unit_id, revision, audit)
        return {"state": "superseded", "unit_id": unit_id, "revision": revision,
                "superseded_by": superseded_by, "reason": reason, "authority": authority}

    def unit_audits(self) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT * FROM unit_audits ORDER BY checked_at DESC").fetchall()
        return [{**dict(row), "audit": json.loads(row["audit_json"])} for row in rows]

    def store_active_unit_for_migration(self, payload: dict):
        """Import an already-versioned active unit into an isolated/new registry."""
        with self._conn() as db:
            db.execute("INSERT INTO unit_revisions(unit_id,revision,publication_id,payload_json,active,created_at) VALUES(?,?,?,?,1,?)",
                       (payload["id"], payload["revision"], "migration-fixture", json.dumps(payload, ensure_ascii=False), time.time()))

    def store_model(self, model: dict):
        with self.transaction() as db:
            db.execute("UPDATE model_revisions SET active=0 WHERE model_id=?", (model["id"],))
            db.execute("INSERT INTO model_revisions(model_id,revision,payload_json,active,created_at) VALUES(?,?,?,1,?) ON CONFLICT(model_id,revision) DO UPDATE SET payload_json=excluded.payload_json,active=1,created_at=excluded.created_at",
                       (model["id"], model["revision"], json.dumps(model, ensure_ascii=False), time.time()))

    def store_candidate_model(self, model: dict):
        if model.get("model_kind") != "atomic_cross_dimensional_candidate" or model.get("status") != "needs_review":
            raise ValueError("invalid_model_candidate")
        with self._conn() as db:
            db.execute("INSERT INTO model_revisions(model_id,revision,payload_json,active,created_at) VALUES(?,?,?,0,?) ON CONFLICT(model_id,revision) DO UPDATE SET payload_json=excluded.payload_json,active=0,created_at=excluded.created_at",
                       (model["id"], model["revision"], json.dumps(model, ensure_ascii=False), time.time()))

    def archive_models(self, model_ids: list[str], *, reason: str):
        if not model_ids or not reason:
            raise ValueError("archive_reason_required")
        with self.transaction() as db:
            placeholders = ",".join("?" for _ in model_ids)
            db.execute(f"UPDATE model_revisions SET active=0 WHERE active=1 AND model_id IN ({placeholders})", tuple(model_ids))
            self._set_meta("legacy_model_archive", json.dumps({"model_ids": sorted(model_ids), "reason": reason, "archived_at": time.time()}, ensure_ascii=False), db)

    def model_inventory(self) -> dict:
        with self._conn() as db:
            rows = db.execute("""
              SELECT model_id,revision,payload_json,active,created_at FROM (
                SELECT model_id,revision,payload_json,active,created_at,
                       ROW_NUMBER() OVER (PARTITION BY model_id ORDER BY created_at DESC) AS position
                FROM model_revisions
              ) WHERE position=1 ORDER BY created_at
            """).fetchall()
        active, candidates, archived_legacy = [], [], []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload.setdefault("id", row["model_id"])
            payload.setdefault("revision", row["revision"])
            if row["active"] and payload.get("model_kind") == "atomic_cross_dimensional":
                active.append(payload)
            elif payload.get("model_kind") == "atomic_cross_dimensional_candidate":
                candidates.append(payload)
            elif not row["active"] and not payload.get("model_kind"):
                archived_legacy.append(payload)
        return {
            "counts": {"active": len(active), "candidates": len(candidates), "archived_legacy": len(archived_legacy)},
            "active": active, "candidates": candidates, "archived_legacy": archived_legacy,
        }

    def active_models(self) -> list[dict]:
        with self._conn() as db:
            # The candidate publisher can write a newer, inactive review
            # revision for the same model id. Selecting every historical row
            # with active=1 leaked the superseded published body into the
            # selector even though model_inventory correctly showed the newer
            # candidate as non-active. The selector must use the exact same
            # latest-revision semantics as the visible inventory.
            rows = db.execute("""
              SELECT payload_json FROM (
                SELECT payload_json,active,created_at,
                       ROW_NUMBER() OVER (PARTITION BY model_id ORDER BY created_at DESC) AS position
                FROM model_revisions
              ) WHERE position=1 AND active=1
              ORDER BY created_at
            """).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def unit_history(self, unit_id: str) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT revision,publication_id,payload_json,active,created_at FROM unit_revisions WHERE unit_id=? ORDER BY created_at DESC", (unit_id,)).fetchall()
        return [{**json.loads(row["payload_json"]), "revision": row["revision"], "publication_id": row["publication_id"], "active": bool(row["active"]), "created_at": row["created_at"]} for row in rows]

    def withdraw_unit(self, unit_id: str, expected_revision: str, reason: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT revision,payload_json FROM unit_revisions WHERE unit_id=? AND active=1", (unit_id,)).fetchone()
            if not row: raise KeyError("active_unit_not_found")
            if row["revision"] != expected_revision: raise RuntimeError("revision_conflict")
            payload = json.loads(row["payload_json"]); payload.update(status="withdrawn", withdrawal_reason=reason, withdrawn_at=time.time())
            db.execute("UPDATE unit_revisions SET active=0,payload_json=? WHERE unit_id=? AND revision=?", (json.dumps(payload, ensure_ascii=False), unit_id, expected_revision))
        return {"state": "withdrawn", "unit_id": unit_id, "revision": expected_revision, "reason": reason}

    def idempotent(self, key: str, operation: str, action):
        if not key: raise ValueError("idempotency_key_required")
        with self.transaction() as db:
            row = db.execute("SELECT result_json FROM idempotency WHERE key=? AND operation=?", (key, operation)).fetchone()
            if row: return json.loads(row["result_json"])
            result = action()
            db.execute("INSERT INTO idempotency(key,operation,result_json,created_at) VALUES(?,?,?,?)", (key, operation, json.dumps(result, ensure_ascii=False), time.time()))
            return result

    def record_job(self, kind: str, state: str, payload: dict, job_id: str | None = None) -> str:
        job_id = job_id or str(uuid.uuid4())
        now = time.time()
        with self._conn() as db:
            db.execute("INSERT INTO jobs(id,kind,state,payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,payload_json=excluded.payload_json,updated_at=excluded.updated_at", (job_id, kind, state, json.dumps(payload, ensure_ascii=False), now, now))
        return job_id

    def jobs(self) -> list[dict]:
        with self._conn() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY updated_at DESC").fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]
