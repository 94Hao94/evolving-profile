"""The only local entry point that can make guidance active."""
from __future__ import annotations

from repository import GuidanceRepository
from schemas import review_contract_accepts, validate_proposal


class PublicationError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def prepare_publication(repo: GuidanceRepository, proposal: dict, review: dict, owner_token: str) -> dict:
    from observation_publish import validate_task_scope
    try:
        validate_task_scope(proposal)
    except ValueError as error:
        repo.record_job("publication", "held", {"proposal": proposal, "reason": str(error)})
        raise PublicationError(str(error)) from error
    checked = validate_proposal(proposal)
    if checked["status"] != "supported":
        repo.record_job("publication", checked["status"], {"proposal": proposal, "reason": checked["reason"]})
        raise PublicationError(checked["reason"])
    if not review_contract_accepts(review):
        repo.record_job("publication", "held", {"proposal": proposal, "reason": "review_contract_rejected"})
        raise PublicationError("review_contract_rejected")
    return repo.prepare(proposal, review, checked["proposal_sha256"], owner_token)


def commit_publication(repo: GuidanceRepository, publication_id: str, expected_active_revision: str | None,
                       expected_source_tokens: dict, owner_token: str) -> dict:
    try:
        return repo.activate(publication_id, expected_active_revision, expected_source_tokens, owner_token)
    except PermissionError as error:
        raise PublicationError("owner_conflict") from error
    except RuntimeError as error:
        raise PublicationError("revision_conflict") from error
    except (KeyError, ValueError) as error:
        raise PublicationError(str(error)) from error


def hold_overbroad_observation(repo: GuidanceRepository, unit_id: str, *, expected_unit_revision: str,
                              expected_active_revision: str | None, backup_path, dry_run: bool = True) -> dict:
    """Plan or CAS-hold one overbroad inferred unit, keeping a scoped candidate.

    No semantic review is manufactured and no replacement becomes active.
    A SQLite backup retains the prior audit state and every original revision.
    """
    import json
    import sqlite3
    import time
    import uuid
    from hashlib import sha256
    from pathlib import Path
    from observation_publish import independent_task_contexts

    def current():
        unit = next((u for u in repo.active_units() if u['id'] == unit_id), None)
        if not unit or unit['revision'] != expected_unit_revision or repo.active_revision() != expected_active_revision:
            raise PublicationError('revision_conflict')
        return unit

    unit = current()
    refs = unit.get('evidence_refs') or []
    contexts = independent_task_contexts(refs)
    if unit.get('nature') != 'inferred_pattern' or len(contexts) != 1:
        raise PublicationError('single_task_inferred_unit_required')
    sessions = sorted({str(r['source_record']['session_id']) for r in refs if r.get('source_record', {}).get('session_id')})
    tasks = sorted({str(r['source_record']['task_id']) for r in refs if r.get('source_record', {}).get('task_id')})
    candidate = {**unit, 'nature': 'task_local', 'scope_level': 'task', 'support_count': 1,
        'scope': {**(unit.get('scope') or {}), 'session_ids': sessions if not tasks else [], 'task_ids': tasks},
        'confidence_inputs': {**(unit.get('confidence_inputs') or {}), 'independent_task_contexts': 1,
                              'scope_basis': 'single_task_context'}, 'cross_cutting': False,
        'status': 'scoped_candidate_requires_semantic_review', 'migration_source_revision': expected_unit_revision}
    reason = 'same_task_evidence_does_not_support_cross_context_preference'
    result = {'status': 'dry_run', 'unit_id': unit_id, 'unit_revision': expected_unit_revision,
              'expected_active_revision': expected_active_revision, 'candidate': candidate, 'reason': reason}
    if dry_run: return result
    target = Path(backup_path).expanduser().resolve()
    if target == repo.path.resolve(): raise PublicationError('backup_must_be_separate')
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents replacement of an older recovery snapshot.
    with target.open('xb'): pass
    with sqlite3.connect(repo.path) as source, sqlite3.connect(target) as backup:
        source.backup(backup)
    with repo.transaction() as db:
        active = db.execute('SELECT revision FROM unit_revisions WHERE unit_id=? AND active=1', (unit_id,)).fetchone()
        watermark = db.execute("SELECT value FROM meta WHERE key='active_revision'").fetchone()
        if not active or active['revision'] != expected_unit_revision or ((watermark['value'] or None) if watermark else None) != expected_active_revision:
            raise PublicationError('revision_conflict')
        audit = {'state': 'needs_review', 'scope_level': 'task', 'validity_kind': 'context_sensitive',
                 'reason': reason, 'backup_path': str(target), 'scoped_candidate': candidate}
        db.execute('INSERT INTO unit_audits VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(unit_id,revision) DO UPDATE SET state=excluded.state,scope_level=excluded.scope_level,validity_kind=excluded.validity_kind,reason=excluded.reason,checked_at=excluded.checked_at,audit_json=excluded.audit_json',
            (unit_id, expected_unit_revision, 'needs_review', 'task', 'context_sensitive', reason, time.time(), None, json.dumps(audit, ensure_ascii=False)))
        db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)', (str(uuid.uuid4()), 'observation_scope_correction',
            'held', json.dumps(result, ensure_ascii=False), time.time(), time.time()))
        revision = 'sha256:' + sha256(json.dumps([expected_active_revision, unit_id, expected_unit_revision,
            reason, str(uuid.uuid4())], separators=(',', ':')).encode()).hexdigest()
        repo._set_meta('active_revision', revision, db)
    return {**result, 'status': 'held_for_scoped_review', 'backup_path': str(target), 'active_revision': revision}
