"""Keep recipe, configuration, protocol and native evidence independent."""
from .registry import CAPABILITIES

MATCH_FIELDS=('host_version','adapter_revision','config_sha256','mode','platform')


def readiness(profile, observations, context):
    capabilities={}
    for capability in CAPABILITIES:
        documented=profile.get('documented',{}).get(capability)
        result={'state':'documented' if documented is True else 'unsupported' if documented is False else 'unknown',
                'documented':documented,'stale':False,'enabled':False,'evidence_kind':None,
                'host_receive':'unknown','answer_use':'not_measured',
                'stale_reason':None,'next_action':None}
        for row in observations:
            if not isinstance(row,dict) or row.get('capability_id')!=capability:continue
            if not row.get('probe_id') or not row.get('observed_at'):continue
            if any(row.get(k)!=context.get(k) for k in MATCH_FIELDS):
                result['stale']=True
                result['stale_reason']=('adapter_revision_mismatch' if row.get('adapter_revision') != context.get('adapter_revision')
                    else 'host_context_mismatch')
                result['next_action']='rerun_native_host_task' if row.get('evidence_kind')=='native_host' else 'rerun_host_probe'
                continue
            kind=row.get('evidence_kind');state=row.get('state')
            if kind=='isolated_probe' and state in ('protocol_verified','host_verified'):
                state='protocol_verified'
            elif kind=='native_host' and state=='host_verified':
                if not all(context.get(k) for k in MATCH_FIELDS):continue
            elif kind=='configuration' and state=='configured':pass
            else:continue
            result.update(state=state,evidence_kind=kind,observed_at=row['observed_at'],
                          probe_id=row['probe_id'],stale=False,stale_reason=None,next_action=None)
        capabilities[capability]=result
    parser=profile.get('source_parser')
    native_rows=[]
    for row in observations:
        if not isinstance(row,dict) or row.get('evidence_kind')!='native_host':continue
        if any(row.get(k)!=context.get(k) for k in MATCH_FIELDS):continue
        if not row.get('probe_id') or not row.get('observed_at'):continue
        native_rows.append(row)
    native_rows.sort(key=lambda row:str(row.get('observed_at','')), reverse=True)
    native=native_rows[0] if native_rows else None
    association={'state':'parser_available' if parser else 'unverified',
                 'parser':parser,'session_id':'unknown','installation_id':'unknown',
                 'transcript':'unknown','receipt':'not_measured'}
    if native:
        supplied=native.get('session_association') if isinstance(native.get('session_association'),dict) else {}
        association.update({key:supplied[key] for key in (
            'state','parser','session_id','installation_id','transcript','transcript_path',
            'receipt','receipt_kind','receipt_at') if key in supplied})
        if native.get('state')=='host_verified' and association.get('state') not in ('host_verified','unverified'):
            association['state']='host_verified'
    verified = [key for key, value in capabilities.items() if value.get('state') == 'host_verified']
    pending = [key for key, value in capabilities.items()
               if value.get('state') not in {'host_verified', 'unsupported'}]
    verification_scope = 'verified' if verified and not pending else 'partial' if verified else 'unverified'
    return {'schema':'ep.host-readiness.v1','host_id':profile['id'],
            'capabilities':capabilities,'context':dict(context),'host_verified':bool(verified),
            'verification_scope':verification_scope,'verified_capabilities':verified,
            'pending_capabilities':pending,'capture_enabled':False,
            'session_association':association,
            'next_actions':sorted(set(v['next_action'] for v in capabilities.values()
                                      if v.get('stale') and v.get('next_action')))}
