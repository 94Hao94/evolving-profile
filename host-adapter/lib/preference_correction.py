"""Owner corrections are versioned changes, never fabricated source reviews."""
import hashlib
import json
import sqlite3
import time
import uuid


def correct_preference(path, request):
    allowed = {'unit_id', 'expected_revision', 'text', 'applies_when', 'exceptions', 'reason'}
    if set(request) - allowed:
        raise ValueError('unsupported_field')
    text = request.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > 12000:
        raise ValueError('invalid_text')
    for field in ('applies_when', 'exceptions'):
        if field in request and (not isinstance(request[field], list) or len(request[field]) > 50 or any(not isinstance(x, str) or len(x) > 2000 for x in request[field])):
            raise ValueError('invalid_conditions')
    with sqlite3.connect(path, isolation_level=None) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE')
        try:
            row = db.execute('SELECT * FROM unit_revisions WHERE unit_id=? AND active=1', (request['unit_id'],)).fetchone()
            if not row:
                raise ValueError('unit_not_found')
            if not request.get('expected_revision') or row['revision'] != request['expected_revision']:
                raise ValueError('revision_conflict')
            payload = json.loads(row['payload_json'])
            for field in ('text', 'applies_when', 'exceptions'):
                if field in request:
                    payload[field] = request[field]
            payload['text'] = text.strip()
            now = time.time()
            revision = 'sha256:' + hashlib.sha256((json.dumps(payload, sort_keys=True, ensure_ascii=False) + uuid.uuid4().hex).encode()).hexdigest()
            payload['revision'] = revision
            payload['manual_correction'] = {'authority': 'owner_manual_correction', 'base_revision': row['revision'], 'reason': str(request.get('reason') or '用户手动修正')[:2000], 'at': now}
            db.execute('UPDATE unit_revisions SET active=0 WHERE unit_id=?', (request['unit_id'],))
            db.execute('INSERT INTO unit_revisions VALUES(?,?,?,?,1,?)', (request['unit_id'], revision, 'manual-correction:' + uuid.uuid4().hex, json.dumps(payload, ensure_ascii=False), now))
            audit = db.execute('SELECT * FROM unit_audits WHERE unit_id=? AND revision=?', (request['unit_id'], row['revision'])).fetchone()
            if audit:
                db.execute('INSERT INTO unit_audits VALUES(?,?,?,?,?,?,?,?,?)', (request['unit_id'], revision, audit['state'], audit['scope_level'], audit['validity_kind'], audit['reason'], now, audit['superseded_by'], audit['audit_json']))
            db.execute("INSERT INTO meta(key,value) VALUES('active_revision',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (revision,))
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            raise
    return {'applied': True, 'unit_id': request['unit_id'], 'revision': revision, 'previous_revision': row['revision']}
