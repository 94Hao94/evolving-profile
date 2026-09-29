"""Current-turn recovery guidance for observed execution failures.

The caller owns detection. This module neither polls tools nor publishes a
failure as long-term memory; it converts one bounded observed event into a
normal task-guidance refresh.
"""
from __future__ import annotations

from selector import get_preference


def refresh_runtime_guidance(repo, request: dict) -> dict:
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
