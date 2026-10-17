"""Current-turn recovery guidance for observed execution failures.

The caller owns detection. This module neither polls tools nor publishes a
failure as long-term memory; it converts one bounded observed event into a
normal task-guidance refresh.
"""
from __future__ import annotations

from selector import get_preference
from context_binding import GuidanceInputError, validate_preference_request


def validate_runtime_guidance_request(request):
    task = validate_preference_request(request)
    if not task.get('objective', '').strip():
        raise GuidanceInputError('task.objective', 'a non-empty string', 'task_objective_required')
    if 'phase' in task and task['phase'] not in ('understand', 'analyze', 'execute', 'verify', 'deliver'):
        raise GuidanceInputError('task.phase', 'understand, analyze, execute, verify or deliver')
    event = request.get('runtime_event')
    if not isinstance(event, dict):
        reason = 'runtime_event_required'
        if 'runtime_events' in request:
            reason += ' (runtime_events is not accepted; use runtime_event with failure)'
        raise GuidanceInputError('runtime_event', 'an object, e.g. {"failure":"observed failure"}', reason)
    if not isinstance(event.get('failure'), str) or not event['failure'].strip():
        raise GuidanceInputError('runtime_event.failure', 'a non-empty string', 'runtime_event_required')
    event_fields = {'capability', 'tool', 'failure', 'occurrence', 'required_for'}
    for field in event:
        if field not in event_fields:
            raise GuidanceInputError('runtime_event', 'an object containing only capability, tool, failure, occurrence and required_for')
        if field != 'occurrence' and not isinstance(event[field], str):
            raise GuidanceInputError('runtime_event.' + field, 'a string')
    if 'occurrence' in event and (type(event['occurrence']) is not int or not 1 <= event['occurrence'] <= 20):
        raise GuidanceInputError('runtime_event.occurrence', 'an integer from 1 to 20')
    allowed = {'check_id', 'task', 'runtime_event', 'loaded', 'memory_policy', 'max_tokens'}
    for field in request:
        if field not in allowed:
            raise GuidanceInputError('arguments', 'an object containing only check_id, task, runtime_event, loaded, memory_policy and max_tokens')
    if 'check_id' in request and not isinstance(request['check_id'], str):
        raise GuidanceInputError('check_id', 'a string')
    if 'loaded' in request and (not isinstance(request['loaded'], list) or
                              any(not isinstance(value, dict) for value in request['loaded'])):
        raise GuidanceInputError('loaded', 'an array of objects')
    if request.get('memory_policy', 'allowed') not in ('allowed', 'forbidden'):
        raise GuidanceInputError('memory_policy', 'allowed or forbidden')
    if 'max_tokens' in request and (type(request['max_tokens']) is not int or not 500 <= request['max_tokens'] <= 8000):
        raise GuidanceInputError('max_tokens', 'an integer from 500 to 8000')


def refresh_runtime_guidance(repo, request: dict) -> dict:
    from context_binding import bind_preference_request
    validate_runtime_guidance_request(request)
    request = bind_preference_request(request)
    event = request.get('runtime_event')
    if not isinstance(event, dict) or not str(event.get('failure') or '').strip():
        raise ValueError('runtime_event_required')
    task = dict(request.get('task') or {})
    if not str(task.get('objective') or '').strip():
        raise ValueError('task_objective_required')
    task.setdefault('current_user_message', task['objective'])
    task.setdefault('context_summary', '')
    task.setdefault('previous_user_messages', [])
    task.setdefault('continuation', True)
    task.setdefault('phase', 'execute')
    task.setdefault('current_constraints', ['当前用户 Prompt 优先'])
    task.setdefault('domains', [])
    task.setdefault('media', [])
    task.setdefault('resolved_entities', [])
    task.setdefault('unresolved_references', [])
    task['runtime_events'] = [event]
    result = get_preference(repo, {
        'task': task,
        'loaded': request.get('loaded') or [],
        'memory_policy': request.get('memory_policy', 'allowed'),
        'max_tokens': request.get('max_tokens', 3000),
    })
    result.update(mode='runtime_guidance_refresh', long_term_model_created=False,
                  persistence='none_current_turn_only', runtime_event={
                      key: event.get(key) for key in ('capability', 'tool', 'failure', 'occurrence', 'required_for')
                  })
    return result
