"""CAS-versioned hierarchical graphs, separate from legacy navigation."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .scenario_coverage_contract import canonical,fingerprint,contract


class HierarchicalStore:
    def __init__(self,path,*,readonly=False):
        self.path=Path(path);self.readonly=readonly
        if self.path.is_symlink() or any(p.is_symlink() for p in self.path.parents):raise ValueError('hierarchical_path_invalid')
        if readonly:
            if not self.path.is_file():raise ValueError('hierarchical_unavailable')
        else:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.connect() as db:
                db.executescript('CREATE TABLE IF NOT EXISTS graphs(scope TEXT PRIMARY KEY,version INTEGER NOT NULL,data TEXT NOT NULL,sha TEXT NOT NULL);'
                    'CREATE TABLE IF NOT EXISTS history(scope TEXT,version INTEGER,data TEXT,sha TEXT,PRIMARY KEY(scope,version));')
            os.chmod(self.path,0o600)

    @contextmanager
    def connect(self):
        if self.path.is_symlink() or any(p.is_symlink() for p in self.path.parents):raise ValueError('hierarchical_path_invalid')
        db=sqlite3.connect(self.path.resolve().as_uri()+('?mode=ro' if self.readonly else '?mode=rwc'),uri=True,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:yield db
        finally:db.close()

    def save_generation(self,binding,graph,*,expected_version):
        if self.readonly:raise ValueError('hierarchical_readonly')
        if binding.get('permission',{}).get('allowed') is not True:raise ValueError('permission_unverified')
        key=fingerprint(binding['scope'])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM graphs WHERE scope=?',(key,)).fetchone()
            current=row['version'] if row else 0
            if current!=expected_version:raise ValueError('stale_generation')
            value={'binding':binding,'graph':graph,'version':current+1};raw=canonical(value)
            if len(raw)>contract()['defaults']['output_bytes']:raise ValueError('hierarchical_store_limit')
            if row:db.execute('INSERT OR IGNORE INTO history VALUES(?,?,?,?)',(key,current,row['data'],row['sha']))
            db.execute('INSERT OR REPLACE INTO graphs VALUES(?,?,?,?)',(key,current+1,raw.decode(),fingerprint(value)))
        return value

    def load_current(self,scope,permission):
        with self.connect() as db:row=db.execute('SELECT * FROM graphs WHERE scope=?',(fingerprint(scope),)).fetchone()
        if row is None:raise ValueError('hierarchical_unavailable')
        if len(row['data'].encode())>contract()['defaults']['output_bytes']:raise ValueError('hierarchical_store_limit')
        value=json.loads(row['data'])
        if fingerprint(value)!=row['sha'] or value['binding']['scope']!=scope:raise ValueError('hierarchical_store_changed')
        if permission.get('allowed') is not True or value['binding']['permission']!=permission:raise ValueError('permission_changed')
        return value

    def mark_stale(self,scope,ids,*,expected_version):
        # Permission is recovered only for the write operation, never used as
        # authorization for reads. Readers must pass a current permission.
        with self.connect() as db:row=db.execute('SELECT data FROM graphs WHERE scope=?',(fingerprint(scope),)).fetchone()
        if row is None:raise ValueError('hierarchical_unavailable')
        value=json.loads(row[0]);graph=value['graph'];graph['stale_ids']=sorted(set(graph.get('stale_ids',[]))|set(ids))
        graph['coverage']={**graph.get('coverage',{}),'status':'stale','target_complete':False}
        return self.save_generation(value['binding'],graph,expected_version=expected_version)
