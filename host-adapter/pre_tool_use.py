#!/usr/bin/env python3
"""Canary-only input binding; preserves original text alongside agent queries."""
import json
import sys
from lib.config import load_config

def main():
    hook=json.load(sys.stdin);config=load_config()
    if hook.get('session_id') not in config.get('nativeDelegationSessions',[]):return
    from native_delegation import observe
    from memory_turn_check import retrieval_preflight,pending_context
    observe(hook)
    result=retrieval_preflight(hook)
    context=pending_context(hook.get('session_id'),hook.get('turn_id'))
    if context:result.setdefault('hookSpecificOutput',{'hookEventName':'PreToolUse'})['additionalContext']=context
    if result:json.dump(result,sys.stdout,ensure_ascii=False)

if __name__=='__main__':main()
