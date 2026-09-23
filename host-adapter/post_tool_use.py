#!/usr/bin/env python3
"""PostToolUse hook: local journal plus one bounded recall for a new error."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.runtime_paths import ham_source_root

HAM_SOURCE_ROOT = ham_source_root(__file__)
if HAM_SOURCE_ROOT not in sys.path:
    sys.path.insert(0, HAM_SOURCE_ROOT)
try:
    from ham.adapter import emit as ham_emit
except Exception:
    def ham_emit(*_args, **_kwargs):
        return {"attempted": False, "reason": "adapter_unavailable"}

from lib.bank import derive_bank_id
from lib.client import HindsightClient
from lib.config import debug_log, load_config
from lib.daemon import get_api_url
from lib.midtask import bound_additional_context, record_tool_event
from source_driven_hook import enabled as source_driven_enabled


def _memory_text(response):
    values = []
    for result in (response or {}).get("results", [])[:5]:
        if isinstance(result, dict):
            values.append(str(result.get("content") or result.get("memory") or result.get("text") or ""))
    return "\n".join(value for value in values if value).strip()[:2048]


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return
    config = load_config()
    preflight = ''
    try:
        from receipts import record_host_tool_response
        observed = record_host_tool_response(
            Path.home() / '.evolving-profile/guidance-v1/receipts',
            {**hook_input, 'host_id': os.environ.get('HINDSIGHT_AGENT_NAME') or 'codex'},
        )
        if observed.get('state') == 'receipt_mismatch':
            print('[Evolving Profile] guidance host receipt mismatch', file=sys.stderr)
    except Exception as error:
        print('[Evolving Profile] guidance host receipt unavailable: '+type(error).__name__, file=sys.stderr)
    if hook_input.get('session_id') in config.get('nativeDelegationSessions',[]):
        try:
            from native_delegation import observe
            observed=observe(hook_input)
            from memory_turn_check import pending_context
            if hook_input.get('session_id') in config.get('memoryPreanswerReminderSessions', []):
                preflight=pending_context(hook_input.get('session_id'),hook_input.get('turn_id'))
            if observed.get('errors'):print('[Evolving Profile] native delegation observation incomplete: '+str(observed['errors']),file=sys.stderr)
        except Exception as error:
            print('[Evolving Profile] native delegation observation unavailable: '+type(error).__name__,file=sys.stderr)
    ham_emit("PostToolUse", hook_input, "tool_result", "tool", str(hook_input.get("tool_name") or "")[:4096])
    try:
        from memory_turn_check import observe_tool
        observe_tool(hook_input)
    except Exception as error:
        print('[Evolving Profile] tool execution audit unavailable: '+type(error).__name__,file=sys.stderr)
    result = record_tool_event(hook_input)
    if not result.get("new_error"):
        if preflight:
            json.dump({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':preflight}},sys.stdout,ensure_ascii=False)
        return
    config = load_config()
    # Source-driven tasks leave retrieval decisions to the host; journal only.
    if not config.get("autoRecall", True) or source_driven_enabled(config, hook_input):
        if preflight:
            json.dump({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':preflight}},sys.stdout,ensure_ascii=False)
        return
    context = preflight
    try:
        api_url = get_api_url(config, debug_fn=lambda *args: debug_log(config, *args), allow_daemon_start=False)
        client = HindsightClient(api_url, config.get("evolvingProfileApiToken"))
        response = client.recall(
            bank_id=derive_bank_id(hook_input, config), query=result["recall_query"],
            max_tokens=512, budget="low", timeout=12,
        )
        memories = _memory_text(response)
        if memories:
            error_context = bound_additional_context(
                f"<evolving_profile_error_recall>\n{memories}\n</evolving_profile_error_recall>"
            )
            context = '\n'.join(v for v in (preflight,error_context) if v)
    except Exception as error:
        debug_log(config, f"PostToolUse recall skipped: {error}")
    if context:
        json.dump({'hookSpecificOutput':{'hookEventName':'PostToolUse','additionalContext':context}},sys.stdout,ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
