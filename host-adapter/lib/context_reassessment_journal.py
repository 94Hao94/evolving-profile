"""Bounded compensation for the explicitly approved remaining-budget operation.

The existing SQLite evidence carrying the plan digest is the commit marker.
This journal only bridges that operation's JSON/SQLite durability boundary;
it is never a source of new work, permission, or model-attempt budget.
Callers hold the incremental DB lock and index lock for the entire operation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from pathlib import Path

JOURNAL_NAME = 'context-reassessment-journal.json'
MAX_JOURNAL_BYTES = 16 * 1024 * 1024
MAX_INDEX_BYTES = 64 * 1024 * 1024
SCHEMA = 'evolving-profile.remaining-budget-journal.v1'


def pending_reassessment(root):
    """lstat sees even broken symlinks; a dry run never opens the journal."""
    try:
        (Path(root) / JOURNAL_NAME).lstat()
    except FileNotFoundError:
        return False
    return True


def _checked_root(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('reassessment_recovery_unsafe_path')
    root = root.resolve()
    for name in ('context-incremental.sqlite', 'context-index.json'):
        try:
            info = (root / name).lstat()
        except OSError as error:
            raise ValueError('reassessment_recovery_unsafe_path') from error
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('reassessment_recovery_unsafe_path')
    return root


def validate_reassessment_paths(root):
    """Reject redirected files before a caller resolves locks or opens SQLite."""
    root = _checked_root(root)
    if pending_reassessment(root):
        info = (root / JOURNAL_NAME).lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('reassessment_recovery_unsafe_path')
        _validated_journal(root)
    return root


def _read_json(path, limit):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise ValueError('reassessment_recovery_invalid_file')
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError('reassessment_recovery_invalid_file')
        result = json.loads(raw)
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        raise ValueError('reassessment_recovery_invalid_file') from error
    if not isinstance(result, dict):
        raise ValueError('reassessment_recovery_invalid_file')
    return result


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _fsync_directory(root):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_json(path, value, limit, *, exclusive=False):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    if len(raw) > limit:
        raise ValueError('reassessment_recovery_file_budget_exceeded')
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            # Never overwrite an unresolved or concurrently created journal.
            os.link(temporary, path, follow_symlinks=False)
        else:
            if path.is_symlink():
                raise ValueError('reassessment_recovery_unsafe_path')
            os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def prepare_reassessment(root, plan, after_rows, commit_evidence_ids):
    """Durably record exact target rows before the existing writer replaces JSON."""
    root = _checked_root(root)
    if pending_reassessment(root):
        raise ValueError('reassessment_recovery_required')
    changes = plan['changes']
    if (not 1 <= len(changes) <= 32 or not plan.get('resume_remaining_budget')
            or any(c.get('action') != 'resume_remaining_budget' for c in changes)):
        raise ValueError('reassessment_recovery_invalid_plan')
    db_stat = (root / 'context-incremental.sqlite').stat()
    payload = {'schema':SCHEMA, 'context_root':str(root),
        'db_identity':[db_stat.st_dev, db_stat.st_ino], 'plan_sha256':plan['plan_sha256'],
        'targets':[{'session_id':c['session_id'], 'before_job':c['expected_job'],
            'before_row':c['expected_index_row'], 'after_row':after_rows[c['session_id']],
            'commit_evidence_id':commit_evidence_ids[c['session_id']]}
            for c in changes]}
    payload['payload_sha256'] = _digest(payload)
    _atomic_json(root / JOURNAL_NAME, payload, MAX_JOURNAL_BYTES, exclusive=True)


def sync_reassessment_index(root):
    """The index directory entry must be durable before the DB commit marker."""
    _fsync_directory(_checked_root(root))


def _validated_journal(root):
    value = _read_json(root / JOURNAL_NAME, MAX_JOURNAL_BYTES)
    digest = value.pop('payload_sha256', None)
    db_stat = (root / 'context-incremental.sqlite').stat()
    targets = value.get('targets')
    if (value.get('schema') != SCHEMA or digest != _digest(value)
            or value.get('context_root') != str(root)
            or value.get('db_identity') != [db_stat.st_dev, db_stat.st_ino]
            or not isinstance(value.get('plan_sha256'), str)
            or not re.fullmatch('[a-f0-9]{64}', value['plan_sha256'])
            or not isinstance(targets, list) or not 1 <= len(targets) <= 32):
        raise ValueError('reassessment_recovery_invalid_journal')
    ids = set()
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError('reassessment_recovery_invalid_journal')
        sid = target.get('session_id')
        try:
            if str(uuid.UUID(sid)) != sid or sid in ids:
                raise ValueError('invalid_id')
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError('reassessment_recovery_invalid_journal') from error
        ids.add(sid)
        if (any(not isinstance(target.get(k), dict) or target[k].get('session_id') != sid
                for k in ('before_job', 'before_row', 'after_row'))
                or target['before_job'].get('status') != 'waiting_source'
                or type(target['before_job'].get('attempts')) is not int
                or not 0 <= target['before_job']['attempts'] < 3
                or type(target.get('commit_evidence_id')) is not int or target['commit_evidence_id'] <= 0
                or target['after_row'].get('status') != 'raw_available_summary_pending'):
            raise ValueError('reassessment_recovery_invalid_journal')
    return value


def _remove_journal(root):
    (root / JOURNAL_NAME).unlink()
    _fsync_directory(root)


def recover_reassessment(db, root):
    """Complete cleanup after commit, or undo only exact uncommitted target rows.

    No DB budget/state is reconstructed from JSON. A changed job, missing or
    duplicate index row, partial marker, or foreign target edit fails closed.
    The journal remains for inspection and every worker entrypoint is blocked.
    """
    if not pending_reassessment(root):
        return 'none'
    root = _checked_root(root)
    journal = _validated_journal(root)
    committed = []
    for target in journal['targets']:
        candidates = db.execute('''SELECT evidence FROM job_evidence WHERE id=? AND session_id=?
            AND length(CAST(evidence AS BLOB))<=?''',
            (target['commit_evidence_id'], target['session_id'], MAX_JOURNAL_BYTES))
        found = False
        for row in candidates:
            try:
                evidence = json.loads(row[0])
            except (ValueError, TypeError):
                continue
            if (isinstance(evidence, dict)
                    and evidence.get('kind') == 'remaining_budget_source_reassessment'
                    and evidence.get('plan_sha256') == journal['plan_sha256']
                    and evidence.get('prior_job') == target['before_job']
                    and evidence.get('prior_index_row') == target['before_row']):
                found = True
        committed.append(found)
    if all(committed):
        # Later claimed/completed work is never reversed after its commit.
        _remove_journal(root)
        return 'committed'
    if any(committed):
        raise ValueError('reassessment_recovery_conflict')
    for target in journal['targets']:
        current = db.execute('SELECT * FROM jobs WHERE session_id=?', (target['session_id'],)).fetchone()
        if current is None or dict(current) != target['before_job']:
            raise ValueError('reassessment_recovery_conflict')
    index_path = root / 'context-index.json'
    index = _read_json(index_path, MAX_INDEX_BYTES)
    if not isinstance(index.get('sessions'), list) or not isinstance(index.get('projects'), list):
        raise ValueError('reassessment_recovery_conflict')
    replacements = {}
    for target in journal['targets']:
        matches = [r for r in index['sessions'] if isinstance(r, dict) and r.get('session_id') == target['session_id']]
        if (len(matches) != 1 or matches[0] not in (target['before_row'], target['after_row'])):
            raise ValueError('reassessment_recovery_conflict')
        if matches[0] != target['before_row']:
            replacements[target['session_id']] = target['before_row']
    if replacements:
        index['sessions'] = [replacements.get(row.get('session_id'), row)
                             if isinstance(row, dict) else row for row in index['sessions']]
        # Write only compensating target rows while preserving other sessions,
        # projects and metadata. This independent writer also tolerates an
        # injected post-replace failure in the normal index update function.
        _atomic_json(index_path, index, MAX_INDEX_BYTES)
    _remove_journal(root)
    return 'rolled_back'
