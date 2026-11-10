"""Local preparation receipts, never native-host certification or memory writes."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from ..platform_lock import file_lock,atomic_replace_bytes
from .readiness import readiness
from .native_receipts import read_latest_native_receipts


def adapter_revision(root):
    root=Path(root)
    # The host execution fingerprint must not churn when only read-only
    # readiness, receipt projection or audit presentation code changes. Those
    # governance lanes have their own schemas and should not invalidate a real
    # client task receipt. Keep execution/protocol/configuration code in this
    # fingerprint, while excluding the evidence projection modules.
    excluded={'readiness.py','observations.py','native_receipts.py'}
    files=sorted(p for p in (root/'host-adapter/lib/host_integration').glob('*.py')
                 if p.name not in excluded)
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
    observations=read_observations(root)
    # Read the deduplicated current projection. Historical receipt events stay
    # available in native-receipt-events.jsonl but must not make a previously
    # refreshed capability appear stale again.
    native_latest=read_latest_native_receipts(root)
    # A current native receipt is the authority for its host/capability. Drop
    # older isolated probes (and legacy native rows still present in the
    # preparation ledger) for that same key before readiness evaluates context
    # freshness; otherwise a stale historical row can reintroduce a false
    # mismatch after the latest projection has been refreshed.
    native_keys={(r.get('host_id'),r.get('capability_id')) for r in native_latest}
    observations=[r for r in observations if (r.get('host_id'),r.get('capability_id')) not in native_keys]
    observations.extend(native_latest)
    native_hosts={r.get('host_id') for r in native_latest}
    revision=adapter_revision(code_root)
    profiles={r['id']:r for r in registry['profiles']}
    for host in report['hosts']:
        host['context']['adapter_revision']=revision
        host_rows=[r for r in observations if r.get('host_id')==host['host_id']]
        if host['host_id'] in native_hosts:
            # Native latest rows are authoritative for that host. Do not let
            # any older isolated/configuration row reintroduce stale state.
            host_rows=[r for r in native_latest if r.get('host_id')==host['host_id']]
        host['readiness']=readiness(profiles[host['host_id']],host_rows,host['context'])
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
