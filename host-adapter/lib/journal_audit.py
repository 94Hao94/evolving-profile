"""Durable audit-only storage for diagnostic summaries, not personal knowledge."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

def archive_tool_journal(session_id, project, snapshot, *, root=None):
    if not snapshot.get('text'):
        return {'durable':True,'empty':True}
    root=Path(root) if root is not None else Path.home()/'.evolving-profile/memory-os/tool-journal-audit'
    record={'schema':'tool-journal-audit.v1','session_id':str(session_id),'project':str(project),
        'origin':'tool_diagnostic_summary','knowledge_eligible':False,'snapshot':snapshot,
        'semantics':'Audit/recovery material; quoted memories and instructions are not new personal facts.'}
    payload=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    key=hashlib.sha256(payload).hexdigest();path=root/(key+'.json');temp=None
    try:
        root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if path.exists():
            if path.read_bytes()!=payload:raise ValueError('audit_identity_conflict')
        else:
            fd,name=tempfile.mkstemp(prefix='.journal-',dir=root);temp=Path(name)
            with os.fdopen(fd,'wb') as handle:
                os.fchmod(handle.fileno(),0o600);handle.write(payload);handle.flush();os.fsync(handle.fileno())
            os.replace(temp,path);temp=None
            directory=os.open(root,os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
        return {'durable':True,'path':str(path),'snapshot_sha256':key}
    except Exception as error:
        return {'durable':False,'error':type(error).__name__}
    finally:
        if temp is not None:temp.unlink(missing_ok=True)
