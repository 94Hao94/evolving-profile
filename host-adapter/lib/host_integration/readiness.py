"""Keep recipe, configuration, protocol and native evidence independent."""
from .registry import CAPABILITIES

MATCH_FIELDS=('host_version','adapter_revision','config_sha256','mode','platform')


def readiness(profile, observations, context):
    capabilities={}
    for capability in CAPABILITIES:
        documented=profile.get('documented',{}).get(capability)
        result={'state':'documented' if documented is True else 'unsupported' if documented is False else 'unknown',
                'documented':documented,'stale':False,'enabled':False,'evidence_kind':None,
                'host_receive':'unknown','answer_use':'not_measured'}
        for row in observations:
            if not isinstance(row,dict) or row.get('capability_id')!=capability:continue
            if not row.get('probe_id') or not row.get('observed_at'):continue
            if any(row.get(k)!=context.get(k) for k in MATCH_FIELDS):
                result['stale']=True;continue
            kind=row.get('evidence_kind');state=row.get('state')
            if kind=='isolated_probe' and state in ('protocol_verified','host_verified'):
                state='protocol_verified'
            elif kind=='native_host' and state=='host_verified':
                if not all(context.get(k) for k in MATCH_FIELDS):continue
            elif kind=='configuration' and state=='configured':pass
            else:continue
            result.update(state=state,evidence_kind=kind,observed_at=row['observed_at'],
                          probe_id=row['probe_id'],stale=False)
        capabilities[capability]=result
    return {'schema':'ep.host-readiness.v1','host_id':profile['id'],
            'capabilities':capabilities,'context':dict(context),'host_verified':any(
                v['state']=='host_verified' for v in capabilities.values()),'capture_enabled':False}
