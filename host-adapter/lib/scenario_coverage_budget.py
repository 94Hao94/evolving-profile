"""Durable request reservations; retries and unknown usage never become free."""
import json
import os
import sqlite3
import uuid
from pathlib import Path
from .scenario_coverage_contract import contract


class CoverageBudget:
    def __init__(self,path,*,job_id,budget_identity,parent_attempts,max_requests=0,max_tokens=0,scope_identity=None):
        self.path=Path(path);self.job_id=job_id
        if (not job_id or not budget_identity or any(type(v) is not int or v<0 for v in [parent_attempts,max_requests,max_tokens])):
            raise ValueError('budget_configuration_invalid')
        if self.path.is_symlink() or any(p.is_symlink() for p in self.path.parents):raise ValueError('budget_path_invalid')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS parents(job TEXT PRIMARY KEY, identity TEXT NOT NULL,
                attempts INTEGER NOT NULL, max_requests INTEGER NOT NULL, max_tokens INTEGER NOT NULL,scope_identity TEXT);
                CREATE TABLE IF NOT EXISTS reservations(id TEXT PRIMARY KEY,job TEXT NOT NULL,stage TEXT NOT NULL,
                fingerprint TEXT NOT NULL, estimate INTEGER NOT NULL, charged INTEGER NOT NULL,status TEXT NOT NULL,
                usage TEXT,response_sha TEXT, UNIQUE(job,stage,fingerprint));''')
            db.execute('BEGIN IMMEDIATE')
            if 'scope_identity' not in {r[1] for r in db.execute('PRAGMA table_info(parents)')}:
                db.execute('ALTER TABLE parents ADD COLUMN scope_identity TEXT')
            row=db.execute('SELECT * FROM parents WHERE job=?',(job_id,)).fetchone()
            if row:
                if row['identity']!=budget_identity:raise ValueError('budget_identity_changed')
                if scope_identity is not None and row['scope_identity'] not in {None,scope_identity}:raise ValueError('budget_scope_changed')
                if scope_identity is not None and row['scope_identity'] is None:
                    db.execute('UPDATE parents SET scope_identity=? WHERE job=?',(scope_identity,job_id))
                db.execute('UPDATE parents SET attempts=MAX(attempts,?) WHERE job=?',(parent_attempts,job_id))
            else:db.execute('INSERT INTO parents VALUES(?,?,?,?,?,?)',(job_id,budget_identity,parent_attempts,max_requests,max_tokens,scope_identity))
        os.chmod(self.path,0o600)

    def connect(self):
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row;db.execute('PRAGMA synchronous=FULL');return db

    def status(self):
        with self.connect() as db:
            p=dict(db.execute('SELECT * FROM parents WHERE job=?',(self.job_id,)).fetchone())
            rows=db.execute('SELECT * FROM reservations WHERE job=?',(self.job_id,)).fetchall()
        return {**p,'requests_used':len(rows),'charged_tokens':sum(r['charged'] for r in rows),
            'unknown_usage_requests':sum(r['status']=='usage_unknown' for r in rows),
            'reserved_requests':sum(r['status'] in {'reserved','dispatched'} for r in rows)}

    @classmethod
    def existing_status(cls,path,job_id):
        handle=cls.__new__(cls);handle.path=Path(path);handle.job_id=job_id
        return handle.status()

    @classmethod
    def continue_generation(cls,path,*,job_id,scope_identity,parent_attempts):
        """Reuse only the original unspent allowance; never changes its identity/caps."""
        if not scope_identity or type(parent_attempts) is not int or parent_attempts<0:raise ValueError('budget_configuration_invalid')
        handle=cls.__new__(cls);handle.path=Path(path);handle.job_id=job_id
        with handle.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM parents WHERE job=?',(job_id,)).fetchone()
            if row is None or 'scope_identity' not in row.keys() or row['scope_identity']!=scope_identity:
                raise ValueError('budget_scope_changed')
            db.execute('UPDATE parents SET attempts=MAX(attempts,?) WHERE job=?',(parent_attempts,job_id))
        return handle

    def recover_orphaned_requests(self):
        """Only call while holding the coverage worker's exclusive decoder lease.

        Dispatched requests are ambiguous and never resent free. An unused
        reservation still counts conservatively; it is not silently cancelled.
        """
        with self.connect() as db:
            db.execute("UPDATE reservations SET status='usage_unknown' WHERE job=? AND status='dispatched'",(self.job_id,))

    def reserve_request(self,stage,input_fingerprint,estimate):
        if type(estimate) is not int or estimate<=0 or not stage or not input_fingerprint:raise ValueError('reservation_invalid')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            p=db.execute('SELECT * FROM parents WHERE job=?',(self.job_id,)).fetchone()
            if p['attempts']>=contract()['defaults']['parent_max_attempts']:raise ValueError('parent_attempts_exhausted')
            n,charged=db.execute('SELECT COUNT(*),COALESCE(SUM(charged),0) FROM reservations WHERE job=?',(self.job_id,)).fetchone()
            if n>=p['max_requests'] or charged+estimate>p['max_tokens']:raise ValueError('budget_paused')
            rid=str(uuid.uuid4())
            try:db.execute('INSERT INTO reservations VALUES(?,?,?,?,?,?,?,NULL,NULL)',
                    (rid,self.job_id,stage,input_fingerprint,estimate,estimate,'reserved'))
            except sqlite3.IntegrityError:raise ValueError('request_already_reserved') from None
        return {'id':rid,'job_id':self.job_id,'stage':stage,'input_fingerprint':input_fingerprint,'estimate':estimate,'status':'reserved'}

    def ensure_request_available(self,stage,input_fingerprint,estimate):
        """Preflight before claiming a shared parent attempt; reserve still CASes."""
        if type(estimate) is not int or estimate<=0:raise ValueError('reservation_invalid')
        state=self.status()
        if state['attempts']>=contract()['defaults']['parent_max_attempts']:raise ValueError('parent_attempts_exhausted')
        if state['requests_used']>=state['max_requests'] or state['charged_tokens']+estimate>state['max_tokens']:raise ValueError('budget_paused')
        with self.connect() as db:
            if db.execute('SELECT 1 FROM reservations WHERE job=? AND stage=? AND fingerprint=?',(self.job_id,stage,input_fingerprint)).fetchone():
                raise ValueError('request_already_reserved')

    def dispatch(self,reservation):
        if not isinstance(reservation,dict) or reservation.get('job_id')!=self.job_id:raise ValueError('reservation_required')
        with self.connect() as db:
            result=db.execute("UPDATE reservations SET status='dispatched' WHERE id=? AND job=? AND stage=? AND fingerprint=? AND estimate=? AND status='reserved'",
                (reservation.get('id'),self.job_id,reservation.get('stage'),reservation.get('input_fingerprint'),reservation.get('estimate')))
            if result.rowcount!=1:raise ValueError('reservation_required_or_already_dispatched')

    def receipt_matches(self,reservation_id,stage,request_sha,response_sha):
        with self.connect() as db:
            row=db.execute('SELECT * FROM reservations WHERE id=? AND job=?',(reservation_id,self.job_id)).fetchone()
        return bool(row and row['stage']==stage and row['fingerprint']==request_sha
            and row['status'] in {'settled','usage_unknown'} and row['response_sha']==response_sha)

    def settle_request(self,reservation,usage_or_unknown,*,response_fingerprint):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM reservations WHERE id=? AND job=?',(reservation.get('id'),self.job_id)).fetchone()
            if row is None:raise ValueError('reservation_required')
            if row['status'] not in {'reserved','dispatched'}:raise ValueError('already_settled')
            usage=usage_or_unknown
            valid=isinstance(usage,dict) and type(usage.get('total_tokens')) is int and usage['total_tokens']>=0
            charged=usage['total_tokens'] if valid else row['estimate']
            db.execute('UPDATE reservations SET charged=?,status=?,usage=?,response_sha=? WHERE id=?',
                (charged,'settled' if valid else 'usage_unknown',json.dumps(usage) if valid else None,response_fingerprint,row['id']))
        return {'status':'settled' if valid else 'usage_unknown','charged_tokens':charged,'external_fact_verified':False}
