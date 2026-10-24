"""One source-authoritative context boundary for all public guidance consumers."""
from __future__ import annotations

from collections import deque
import datetime
import json
import os
from pathlib import Path


class GuidanceInputError(ValueError):
    """Safe, actionable argument failure; never echo arbitrary caller values."""
    def __init__(self, field, expected, reason='invalid_arguments'):
        self.field = field
        self.expected = expected
        super().__init__(f'{reason}: {field} must be {expected}')


def validate_preference_request(request):
    if not isinstance(request, dict):
        raise GuidanceInputError('arguments', 'an object')
    task = request.get('task', {})
    if not isinstance(task, dict):
        raise GuidanceInputError('task', 'an object, e.g. {"objective":"current task"}')
    for field in ('objective', 'current_user_message', 'context_summary', 'phase'):
        if field in task and not isinstance(task[field], str):
            raise GuidanceInputError('task.' + field, 'a string')
    for field in ('previous_user_messages', 'current_constraints', 'domains', 'media',
                  'resolved_entities', 'unresolved_references'):
        if field in task and (not isinstance(task[field], list) or
                              any(not isinstance(value, str) for value in task[field])):
            raise GuidanceInputError('task.' + field, 'an array of strings')
    if 'runtime_events' in task and (not isinstance(task['runtime_events'], list) or
                                   any(not isinstance(value, dict) for value in task['runtime_events'])):
        raise GuidanceInputError('task.runtime_events', 'an array of objects')
    return task


def resolve_prompt_binding(check_id, event_at, home=None):
    check_id = str(check_id or '').strip()
    host_id=os.environ.get('EVOLVING_PROFILE_HOST_ID')
    installation_id=os.environ.get('EVOLVING_PROFILE_INSTALLATION_ID')
    owner_id=os.environ.get('EVOLVING_PROFILE_OWNER_ID')
    namespaced=bool(host_id and host_id!='codex')
    if namespaced and (not installation_id or not owner_id):
        return {'state':'unattested_host_binding','host_id':host_id,'check_id':check_id}
    if not check_id: return {'state': 'unbound_missing_check_id'}
    home = Path(home) if home is not None else Path.home()
    rows = []
    try:
        recent = deque(maxlen=4000)
        with (home / '.evolving-profile/audit/prompt-ingress.jsonl').open(encoding='utf-8') as stream:
            recent.extend(stream)
        for line in recent:
            try:
                row = json.loads(line)
                if isinstance(row, dict): rows.append(row)
            except (ValueError, TypeError): continue
    except OSError:
        return {'state': 'unknown_prompt_ingress', 'check_id': check_id}
    if namespaced:
        rows=[row for row in rows if row.get('host_id')==host_id and row.get('installation_id')==installation_id and row.get('owner_id')==owner_id]
    else:
        rows=[row for row in rows if row.get('host_id',row.get('host','codex')) in (None,'codex')]
    matches = [row for row in rows if str(row.get('hook_invocation_id') or '') == check_id]
    tasks = {str(row['task_id']) for row in matches if row.get('task_id')}
    if len({(str(row.get('session_id') or ''), str(row.get('turn_id') or '')) for row in matches}) > 1 or len(tasks) > 1:
        return {'state': 'ambiguous_prompt_binding', 'check_id': check_id}
    bound = matches[-1] if matches else None
    if not bound: return {'state': 'unknown_check_id', 'check_id': check_id}
    session_id = str(bound.get('session_id') or '')
    def timestamp(value):
        stamp = datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=datetime.timezone.utc)
    try: event_time = timestamp(event_at)
    except (TypeError, ValueError, OverflowError): return {'state': 'unknown_event_time', 'check_id': check_id}
    try: bound_time = timestamp(bound.get('at') or '')
    except (TypeError, ValueError, OverflowError): return {'state': 'unknown_prompt_time', 'check_id': check_id}
    if bound_time > event_time: return {'state': 'unknown_check_id_at_call_time', 'check_id': check_id}
    latest = None; latest_time = None
    for row in rows:
        if str(row.get('session_id') or '') != session_id: continue
        try: row_time = timestamp(row.get('at') or '')
        except (TypeError, ValueError, OverflowError): continue
        if row_time <= event_time and (latest_time is None or row_time > latest_time):
            latest = row; latest_time = row_time
    value = {'state': 'prompt_bound', 'check_id': check_id, 'session_id': session_id,
        'turn_id': bound.get('turn_id'), 'hook_invocation_id': bound.get('hook_invocation_id')}
    for key in ('project_id', 'project_key', 'cwd', 'transcript_path', 'model', 'model_provider', 'host', 'host_id','owner_id','installation_id'):
        if bound.get(key): value[key] = bound[key]
    # This value belongs to the exact ingress occurrence, never to a caller's
    # guessed task or to the latest unrelated turn in the same Session.
    if tasks: value['task_id'] = next(iter(tasks))
    if latest and str(latest.get('hook_invocation_id') or '') != check_id:
        value.update(state='stale_prompt_binding', latest_turn_id=latest.get('turn_id'),
            latest_hook_invocation_id=latest.get('hook_invocation_id'))
    return value


def same_prompt_scope(row,binding):
    if any(row.get(key)!=binding.get(key) for key in ('session_id','turn_id','hook_invocation_id')):return False
    if binding.get('host_id') not in (None,'codex'):
        return all(binding.get(key) and row.get(key)==binding[key] for key in ('host_id','installation_id','owner_id'))
    return row.get('host_id',row.get('host','codex')) in (None,'codex')


def bind_preference_request(request, *, home=None, event_at=None):
    supplied_task = validate_preference_request(request)
    identity_keys = {'session_id', 'session_ids', 'project_id', 'project_ids', 'task_id', 'task_ids', 'agent_roles'}
    task = {key: value for key, value in supplied_task.items() if key not in identity_keys}
    now = event_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
    binding = resolve_prompt_binding(request.get('check_id'), now, home)
    if binding.get('state') == 'prompt_bound' and all(binding.get(key) for key in ('session_id', 'turn_id', 'hook_invocation_id')):
        task.update({key: binding[key] for key in ('session_id', 'project_id', 'task_id') if binding.get(key)})
    return {**request, 'task': task}
