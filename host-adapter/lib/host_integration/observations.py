"""Local preparation receipts, never native-host certification or memory writes."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from ..platform_lock import file_lock,atomic_replace_bytes
from .readiness import readiness


def adapter_revision(root):
    root=Path(root)
    files=sorted((root/'host-adapter/lib/host_integration').glob('*.py'))
    files+=[root/'host-adapter/evolving_profile_controller_mcp.py',root/'guidance/context_binding.py',root/'guidance/ep_platform_lock.py']
    digest=hashlib.sha256()
    for p in files:digest.update(str(p.relative_to(root)).encode()+b'\0'+p.read_bytes())
    return digest.hexdigest()


def _path(root):return Path(root)/'host-integrations/observations.json'


def read_observations(root):
    p=_path(root)
    if not p.exists():return []
    if p.is_symlink() or p.stat().st_size>256*1024:raise ValueError('observations_unreadable')
    data=json.loads(p.read_text())
    if data.get('schema')!='ep.host-observations.v1' or not isinstance(data.get('observations'),list):raise ValueError('observations_unreadable')
    # This store contains only isolated preparation evidence. A file edit cannot
    # upgrade its provenance to native-host verification.
    return [{**r,'evidence_kind':'isolated_probe','state':'protocol_verified' if r.get('status')=='protocol_verified' else 'unknown'}
            for r in data['observations'] if isinstance(r,dict)]


def project_observations(report,registry,root,code_root):
    observations=read_observations(root);revision=adapter_revision(code_root)
    profiles={r['id']:r for r in registry['profiles']}
    for host in report['hosts']:
        host['context']['adapter_revision']=revision
        host['readiness']=readiness(profiles[host['host_id']],
            [r for r in observations if r.get('host_id')==host['host_id']],host['context'])
    return report


def record_probe(root,host,probe):
    path=_path(root)
    with file_lock(path.with_suffix('.transaction.lock')):
        rows=read_observations(root)
        rows=[r for r in rows if (r.get('host_id'),r.get('capability_id'),r.get('platform'),r.get('mode'))!=
              (host['host_id'],'mcp_stdio',host['context']['platform'],host['context']['mode'])]
        rows.append({**host['context'],'host_id':host['host_id'],'capability_id':'mcp_stdio',
            'probe_id':probe['probe_id'],'status':probe['status'],'state':'protocol_verified' if probe['status']=='protocol_verified' else 'unknown',
            'evidence_kind':'isolated_probe','observed_at':datetime.now(timezone.utc).isoformat(),
            'error_code':probe.get('error_code')})
        atomic_replace_bytes(path,(json.dumps({'schema':'ep.host-observations.v1','observations':rows[-128:]},indent=2)+'\n').encode(),check_revision=False)
