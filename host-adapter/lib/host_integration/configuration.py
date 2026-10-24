"""Reviewable merge plans; no automatic rewriting of user-owned host settings."""
import copy
import hashlib
import json
import os
from pathlib import Path,PureWindowsPath,PurePosixPath
import re
import stat
import uuid
from ..platform_lock import file_lock,atomic_replace_bytes
from .registry import unique_object

ENTRY='evolving_profile_controller'
OWNER='ep.host-integration.v1'


def _digest(data):return hashlib.sha256(data).hexdigest() if data is not None else None


def _safe_path(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in [path,*path.parents]):raise ValueError('symlink_target_rejected')
    return path


def _read(path):
    if not path.exists():return None
    if not path.is_file() or path.stat().st_size>1024*1024:raise ValueError('configuration_unreadable')
    return path.read_bytes()


def _object(raw):
    value=json.loads((raw or b'{}').decode('utf-8-sig'),object_pairs_hook=unique_object)
    if not isinstance(value,dict):raise ValueError('configuration_object_required')
    if not isinstance(value.get('mcpServers',{}),dict):raise ValueError('invalid_mcp_servers')
    return value


def _validate_desired(desired):
    if not isinstance(desired,dict):raise ValueError('invalid_desired_configuration')
    if not isinstance(desired.get('env',{}),dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in desired.get('env',{}).items()):
        raise ValueError('invalid_desired_environment')
    for key,value in desired.get('env',{}).items():
        if re.search(r'(?i)(key|token|password|secret|authorization)',key) and value and not str(value).startswith('${'):
            raise ValueError('credential_value_not_allowed_in_plan')
    if 'headers' in desired:raise ValueError('credentials_must_use_operator_owned_reference')
    command=desired.get('command')
    if not isinstance(command,str) or not (PurePosixPath(command).is_absolute() or PureWindowsPath(command).is_absolute()):
        raise ValueError('absolute_command_required')
    if not isinstance(desired.get('args',[]),list) or not all(isinstance(x,str) for x in desired.get('args',[])):
        raise ValueError('invalid_command_arguments')


def _merge(value,desired,host_id):
    value=copy.deepcopy(value);servers=value.setdefault('mcpServers',{})
    existing=servers.get(ENTRY)
    if isinstance(existing,dict) and not isinstance(existing.get('env',{}),dict):raise ValueError('invalid_existing_environment')
    if existing is not None and (not isinstance(existing,dict) or
            existing.get('env',{}).get('EVOLVING_PROFILE_INTEGRATION_OWNER')!=OWNER or
            existing.get('env',{}).get('EVOLVING_PROFILE_HOST_ID')!=host_id):
        raise ValueError('unowned_ep_entry_requires_review')
    entry=copy.deepcopy(existing or {})
    if existing and existing.get('url'):raise ValueError('transport_change_requires_review')
    for key in desired:
        if key not in ('command','args','env'):raise ValueError('unmanaged_field_requires_review')
    entry.update({k:copy.deepcopy(v) for k,v in desired.items() if k!='env'})
    entry['env']={**entry.get('env',{}),**desired.get('env',{}),'EVOLVING_PROFILE_INTEGRATION_OWNER':OWNER,
                  'EVOLVING_PROFILE_HOST_ID':host_id,'EVOLVING_PROFILE_ACCESS_MODE':'read-only'}
    servers[ENTRY]=entry
    return value


def plan_configuration(profile,target,desired):
    _validate_desired(desired);target=_safe_path(target);before=_read(target)
    supported=profile.get('config',{}).get('format')=='json' and profile.get('config',{}).get('apply') is True
    changed=[]
    if supported:
        previous=_object(before);merged=_merge(previous,desired,profile['id'])
        old=previous.get('mcpServers',{}).get(ENTRY,{})
        new=merged['mcpServers'][ENTRY]
        changed=[k for k in ('command','args') if old.get(k)!=new.get(k)]
        changed+=['env/'+k for k,v in new.get('env',{}).items() if old.get('env',{}).get(k)!=v]
    return {'schema':'ep.host-config-plan.v1','owner':OWNER,'plan_id':uuid.uuid4().hex,
            'host_id':profile['id'],'target':str(target),'before_sha256':_digest(before),
            'apply_supported':supported,'desired':copy.deepcopy(desired),'format':profile.get('config',{}).get('format'),
            'changes':[{'entry':ENTRY,'operation':'merge_owned_entry'}],
            'changed_fields':changed,'permission_fields':'preserved_not_implicitly_changed',
            'legacy_alias_action':'report_only','created_for':'operator_review_not_runtime_apply'}


def apply_configuration(plan,*,expected_sha256):
    if plan.get('schema')!='ep.host-config-plan.v1' or plan.get('owner')!=OWNER or plan.get('apply_supported') is not True:
        raise ValueError('configuration_apply_not_supported')
    if plan.get('before_sha256')!=expected_sha256:raise ValueError('revision_conflict')
    _validate_desired(plan['desired']);target=_safe_path(plan['target'])
    with file_lock(target.with_name(target.name+'.ep-transaction.lock')):
        before=_read(target)
        if _digest(before)!=expected_sha256:raise ValueError('revision_conflict')
        result=_merge(_object(before),plan['desired'],plan['host_id'])
        data=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
        backup=target.with_name(target.name+'.ep-backup-'+uuid.uuid4().hex)
        if before is not None:atomic_replace_bytes(backup,before)
        after=atomic_replace_bytes(target,data,expected_sha256=expected_sha256)
        return {'schema':'ep.host-config-receipt.v1','owner':OWNER,'target':str(target),
                'backup':str(backup) if before is not None else None,'before_sha256':expected_sha256,
                'after_sha256':after,'host_id':plan['host_id'],'plan_id':plan['plan_id']}


def rollback_configuration(receipt,*,expected_sha256):
    if receipt.get('schema')!='ep.host-config-receipt.v1' or receipt.get('owner')!=OWNER:
        raise ValueError('invalid_configuration_receipt')
    if expected_sha256!=receipt.get('after_sha256'):raise ValueError('revision_conflict')
    target=_safe_path(receipt['target'])
    with file_lock(target.with_name(target.name+'.ep-transaction.lock')):
        current=_read(target)
        if _digest(current)!=expected_sha256:raise ValueError('revision_conflict')
        if receipt.get('backup'):
            backup=_safe_path(receipt['backup'])
            if backup.parent!=target.parent:raise ValueError('backup_scope_mismatch')
            data=_read(backup)
            if _digest(data)!=receipt.get('before_sha256'):raise ValueError('backup_revision_mismatch')
            return {'status':'restored','sha256':atomic_replace_bytes(target,data,expected_sha256=expected_sha256)}
        # Keep a recoverable copy instead of unlinking an operator configuration.
        recovery=target.with_name(target.name+'.ep-rollback-'+uuid.uuid4().hex)
        os.replace(target,recovery)
        return {'status':'restored_absence','recovery':str(recovery)}
