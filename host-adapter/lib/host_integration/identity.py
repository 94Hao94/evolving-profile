"""Authorization-owned namespace; client text is never trusted host attestation."""
import hashlib
import json
import uuid


def bind_host_identity(claim,authority):
    if not isinstance(claim,dict) or not isinstance(authority,dict):raise ValueError('identity_object_required')
    trusted=authority.get('trusted') is True and all(isinstance(authority.get(k),str) and authority[k]
                                                   for k in ('owner_id','host_id','installation_id'))
    result={'schema':'ep.host-binding.v1','attestation':'trusted_entry' if trusted else 'unattested',
            'owner_id':authority.get('owner_id') if trusted else None,
            'host_id':authority.get('host_id') or claim.get('host_id') or 'unknown',
            'installation_id':authority.get('installation_id') if trusted else None}
    if trusted and claim.get('host_id') not in (None,authority['host_id']):raise PermissionError('host_scope_mismatch')
    assigned=False
    for key in ('session_id','task_id','turn_id','message_id','tool_call_id'):
        value=claim.get(key)
        if value is not None and (not isinstance(value,str) or len(value)>256):raise ValueError('invalid_native_identity')
        if key in ('session_id','turn_id') and not value:value='adapter:'+uuid.uuid4().hex;assigned=True
        result[key]=value
    result['identity_origin']='adapter_assigned' if assigned else 'host'
    result['usable_for_capture']=bool(trusted and not assigned)
    result['binding_key']=hashlib.sha256(json.dumps([result.get(k) for k in
        ('owner_id','host_id','installation_id','session_id','task_id','turn_id')],ensure_ascii=False).encode()).hexdigest()
    return result


def validate_binding(binding,authenticated_scope):
    if binding.get('attestation')!='trusted_entry':raise PermissionError('unattested_binding')
    for key in ('owner_id','host_id','installation_id'):
        if not authenticated_scope.get(key) or binding.get(key)!=authenticated_scope[key]:raise PermissionError('identity_scope_mismatch')
    return binding
