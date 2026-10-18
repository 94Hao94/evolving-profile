"""Transactional, source-bound structural ledger, not semantic acceptance."""
import json
import os
import sqlite3
from pathlib import Path

from .scenario_coverage_contract import canonical, fingerprint,contract
from .scenario_source_codec import decode_record, physical_revision, verify_source_batch


def freeze_snapshot(location,permission,watermark=None,*,scope=None):
    if (location.get('status')!='ready' or permission.get('allowed') is not True
            or not isinstance(permission.get('version'),str) or not permission['version']):
        raise ValueError('snapshot_permission_or_source_unverified')
    if physical_revision(location['path'])!=location['physical_revision']:raise ValueError('source_changed')
    value={'location':dict(location),'permission':dict(permission),'watermark':watermark,'scope':scope or {'session_id':location['session_id']},
           'selection_version':contract()['source_selection_version'],'normalization_version':'coverage-source.v1'}
    return {**value,'snapshot_id':fingerprint(value)}


class CoverageStore:
    def __init__(self,path,*,readonly=False):
        self.path=Path(path)
        self.readonly=readonly
        if self.path.is_symlink() or any(p.is_symlink() for p in self.path.parents):raise ValueError('coverage_path_invalid')
        if readonly:
            if not self.path.is_file():raise ValueError('coverage_unavailable')
            return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY, data TEXT NOT NULL,
                generation INTEGER NOT NULL DEFAULT 0, checkpoint TEXT, complete INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS units(snapshot_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                data TEXT NOT NULL, PRIMARY KEY(snapshot_id,sequence));
                CREATE TABLE IF NOT EXISTS raw_units(snapshot_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                raw BLOB NOT NULL, PRIMARY KEY(snapshot_id,sequence));''')
        os.chmod(self.path,0o600)

    def connect(self):
        db=sqlite3.connect(self.path.resolve().as_uri()+('?mode=ro' if self.readonly else '?mode=rwc'),uri=True,timeout=30);db.row_factory=sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        return db

    def create_snapshot(self,snapshot):
        if self.readonly:raise ValueError('coverage_readonly')
        copy={k:v for k,v in snapshot.items() if k!='snapshot_id'}
        if fingerprint(copy)!=snapshot.get('snapshot_id'):raise ValueError('snapshot_identity_invalid')
        with self.connect() as db:db.execute('INSERT OR IGNORE INTO snapshots(id,data) VALUES(?,?)',
                (snapshot['snapshot_id'],canonical(snapshot).decode()))
        return self.read(snapshot['snapshot_id'])

    def read(self,snapshot_id):
        with self.connect() as db:
            row=db.execute('SELECT * FROM snapshots WHERE id=?',(snapshot_id,)).fetchone()
            if row is None:raise ValueError('snapshot_unknown')
            units=[json.loads(r[0]) for r in db.execute('SELECT data FROM units WHERE snapshot_id=? ORDER BY sequence',(snapshot_id,))]
        snap=json.loads(row['data']);selected=[u for u in units if u['selection']=='visible_message']
        semantic=fingerprint({'session_id':snap['location']['session_id'],'permission':snap['permission'],'scope':snap['scope'],
            'messages':[(u['role'],u['text'],u['turn_id']) for u in selected]}) if row['complete'] else None
        return {**snap,'generation':row['generation'],'checkpoint':json.loads(row['checkpoint']) if row['checkpoint'] else None,
            'source_manifest_complete':bool(row['complete']),'semantic_review_status':'not_reviewed',
            'external_fact_verified':False,'units':units,'unit_count':len(units),'selected_count':len(selected),
            'semantic_budget_identity':semantic}

    def validate_snapshot(self,snapshot_id,permission):
        snap=self.read(snapshot_id)
        try:
            valid=(permission==snap['permission'] and permission.get('allowed') is True
                and physical_revision(snap['location']['path'])==snap['location']['physical_revision']
                and not Path(snap['location']['path']).is_symlink())
        except OSError:valid=False
        return {'valid':valid,'reason':None if valid else 'snapshot_stale_or_permission_changed'}

    def append_source_batch(self,snapshot_id,batch,*,expected_version,permission):
        if self.readonly:raise ValueError('coverage_readonly')
        if not self.validate_snapshot(snapshot_id,permission)['valid']:raise ValueError('snapshot_stale_or_permission_changed')
        if not verify_source_batch(batch,self.read(snapshot_id)['location']):raise ValueError('invalid_source_batch')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM snapshots WHERE id=?',(snapshot_id,)).fetchone()
            if row['generation']!=expected_version:raise ValueError('stale_generation')
            snap=json.loads(row['data']);cp=json.loads(row['checkpoint']) if row['checkpoint'] else {}
            sequence=cp.get('next_sequence',0);offset=cp.get('logical_offset',0);turn=cp.get('turn_id')
            try:
                for unit in batch['units']:
                    raw=unit['_raw_line']
                    actual,newturn=decode_record(raw,sequence,offset,turn,snap['location']['session_id'])
                    if unit!=actual:raise ValueError('unit_changed')
                    db.execute('INSERT INTO units VALUES(?,?,?)',(snapshot_id,sequence,
                        canonical({k:v for k,v in actual.items() if k!='_raw_line'}).decode()))
                    if actual['selection']=='visible_message':
                        source_size=db.execute('SELECT COALESCE(SUM(length(raw)),0) FROM raw_units WHERE snapshot_id=?',(snapshot_id,)).fetchone()[0]
                        total_size=db.execute('SELECT COALESCE(SUM(length(raw)),0) FROM raw_units').fetchone()[0]
                        limits=contract()['defaults']
                        if source_size+len(raw)>limits['spool_source_bytes'] or total_size+len(raw)>limits['spool_total_bytes']:
                            raise ValueError('raw_materialization_limit')
                        db.execute('INSERT INTO raw_units VALUES(?,?,?)',(snapshot_id,sequence,raw))
                    sequence+=1;offset+=len(raw);turn=newturn
                newcp=batch['checkpoint']
                if (newcp['next_sequence']!=sequence or newcp['logical_offset']!=offset
                        or newcp.get('turn_id')!=turn or newcp['physical_revision']!=snap['location']['physical_revision']):
                    raise ValueError('checkpoint_changed')
            except (KeyError,TypeError,ValueError,sqlite3.IntegrityError):raise ValueError('invalid_source_batch') from None
            complete=batch['status']=='complete' and batch['partial'] is False and batch['source_identity_verified'] is True
            db.execute('UPDATE snapshots SET generation=generation+1,checkpoint=?,complete=? WHERE id=?',
                (canonical(newcp).decode(),int(complete),snapshot_id))
        return self.read(snapshot_id)
