#!/usr/bin/env python3
"""Canary-only input binding; preserves original text alongside agent queries."""
import json
import sys
import time
from lib.config import load_config
from memory_turn_check import local_memory_access_guard


def guard_with_retry(hook, attempts=2, delay_seconds=0.08):
    """Recheck a just-arrived EP receipt before denying native-memory access."""
    reason = None
    for attempt in range(max(1, attempts)):
        reason = local_memory_access_guard(hook)
        if not reason:
            return None
        if attempt + 1 < attempts and "回执暂缺" in reason:
            time.sleep(delay_seconds)
            continue
        break
    if reason and "回执暂缺" in reason and attempts > 1:
        return reason.replace("回执暂缺", "回执暂缺，已自动重试 1 次")
    return reason

def main():
    hook=json.load(sys.stdin);config=load_config()
    try:
        reason=guard_with_retry(hook)
    except Exception as error:
        reason=None
        if hook.get('tool_name') in {'Bash','exec','CommandExecution','functions.exec'}:
            tool_input=hook.get('tool_input') or {}
            serialized=json.dumps(tool_input,ensure_ascii=False) if not isinstance(tool_input,str) else tool_input
            import re
            if re.search(r'''(?<![A-Za-z0-9_.])(?:/(?:[^/\s"'`,;{}]+/)+\.codex/memories(?:/[^\s"'`,;{}]*)?|(?:~|\$HOME|\$\{HOME\})/\.codex/memories(?:/[^\s"'`,;{}]*)?)''',serialized,re.I):
                reason='Evolving Profile 本地记忆访问门控暂时不可用；不能静默用 Codex 原生 Memory 替代。请调用 EP 工具，或明确说明工具不可用。'
    if reason:
        json.dump({'hookSpecificOutput':{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':reason}},sys.stdout,ensure_ascii=False)
        sys.stdout.flush()
        return
    if hook.get('session_id') not in config.get('nativeDelegationSessions',[]):return
    from native_delegation import observe
    from memory_turn_check import retrieval_preflight,pending_context
    observe(hook)
    result=retrieval_preflight(hook)
    context=pending_context(hook.get('session_id'),hook.get('turn_id'))
    if context:result.setdefault('hookSpecificOutput',{'hookEventName':'PreToolUse'})['additionalContext']=context
    if result:json.dump(result,sys.stdout,ensure_ascii=False)

if __name__=='__main__':main()
