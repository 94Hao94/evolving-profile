#!/usr/bin/env python3
"""SessionStart hook: health check and daemon pre-start.

Fires once when a Codex session begins. Verifies the Hindsight server is
reachable, and kicks off a background daemon pre-start if not — so it's
ready by the first recall or retain hook.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.instruction_entry import instruction_block, record as record_instruction

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
from lib.daemon import get_api_url, prestart_daemon_background
from profile_view import load_view, record_output
from lib.midtask import (
    MAX_ADDITIONAL_CONTEXT_TOKENS,
    MAX_CHECKPOINT_CHARS,
    bound_additional_context,
    load_checkpoint,
)


CORE_REPORT = None


def _core_context(config, hook_input):
    global CORE_REPORT
    CORE_REPORT = None
    protocol = ''
    agent_name=os.environ.get('HINDSIGHT_AGENT_NAME','codex')
    instructions = instruction_block(agent_name+'-session-start')
    if hook_input.get('session_id') in config.get('nativeDelegationSessions',[]):
        from memory_turn_check import NATIVE_PREFLIGHT_POLICY
        protocol = '<evolving_profile_native_preflight>\n'+NATIVE_PREFLIGHT_POLICY+'\n</evolving_profile_native_preflight>'
    if not config.get('autoRecall', True) or not config.get('sourceProfileEnabled', True):
        return '\n'.join(v for v in (instructions,protocol) if v)
    try:
        CORE_REPORT = load_view(derive_bank_id(hook_input, config))
        return '\n'.join(v for v in (instructions,(CORE_REPORT or {}).get('context', ''),protocol) if v)
    except Exception as error:
        debug_log(config, 'Source-backed default view unavailable: '+type(error).__name__)
        return '\n'.join(v for v in (instructions,protocol) if v)

def _record_instruction(hook_input,stage):
    host=os.environ.get('HINDSIGHT_AGENT_NAME','codex')
    try:record_instruction(Path.home()/'.evolving-profile/guidance-v1/instruction-receipts',stage,host,
        {k:hook_input.get(k) for k in ('session_id','turn_id','source')})
    except Exception:pass


def _memory_text(response):
    values = []
    for result in (response or {}).get("results", [])[:5]:
        if isinstance(result, dict):
            values.append(str(result.get("content") or result.get("memory") or result.get("text") or ""))
    return "\n".join(value for value in values if value).strip()[:2048]


def main():
    config = load_config()

    # Consume stdin
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        hook_input = {}

    ham_emit("SessionStart", hook_input, "ambient_context", "checkpoint", "")
    session_id = str(hook_input.get("session_id") or "unknown")
    source = str(hook_input.get("source") or "").lower()
    debug_log(config, f"SessionStart hook, session: {session_id}, source: {source or 'startup'}")

    def _dbg(*a):
        debug_log(config, *a)

    # Recovery is local-first: a durable checkpoint must remain available even
    # when URL discovery, server health, client construction, or Recall fails.
    if source in {"compact", "resume"}:
        checkpoint = load_checkpoint(session_id) or ''
        memories = ""
        # A durable mid-task checkpoint is already the exact local recovery
        # context. Sending its shell transcript back through semantic recall
        # creates a large, non-user query that can time out and pollute the
        # recent-recall view. The next real user prompt still recalls normally.
        internal_checkpoint = (
            "<evolving_profile_checkpoint>" in checkpoint
            or "<evolving_profile_midtask_journal>" in checkpoint
        )
        if config.get("autoRecall", True) and not internal_checkpoint:
            try:
                api_url = get_api_url(config, debug_fn=_dbg, allow_daemon_start=False)
                client = HindsightClient(api_url, config.get("evolvingProfileApiToken"))
                response = client.recall(
                    bank_id=derive_bank_id(hook_input, config),
                    query=checkpoint[:2000],
                    max_tokens=512,
                    budget="low",
                    timeout=12,
                )
                memories = _memory_text(response)
            except Exception as error:
                debug_log(config, f"Compact/resume recall skipped: {error}")
                try:
                    prestart_daemon_background(config, debug_fn=_dbg)
                except Exception as prestart_error:
                    debug_log(config, f"Compact/resume pre-start skipped: {prestart_error}")
        elif internal_checkpoint:
            debug_log(config, "Compact/resume uses local checkpoint only; skipped semantic recall")
        core = _core_context(config, hook_input)
        context = checkpoint
        if memories:
            recall_prefix = "<evolving_profile_resume_recall>\n"
            recall_suffix = "\n</evolving_profile_resume_recall>"
            recall_budget = 512 - len(recall_prefix) - len(recall_suffix)
            recall_block = (
                recall_prefix
                + bound_additional_context(memories, recall_budget)
                + recall_suffix
            )
            context += "\n" + recall_block
        # Compact/resume already carries a durable checkpoint. Preserve the
        # existing hard context bound; include the stable core only when it
        # fits completely, never as a misleading truncated fragment.
        resume_cap = MAX_CHECKPOINT_CHARS + MAX_ADDITIONAL_CONTEXT_TOKENS + len(core) + 1
        profile_included = bool(core and len(core) + 1 + len(context) <= resume_cap)
        if profile_included:
            context = f"{core}\n{context}"
        else:
            instructions=instruction_block(os.environ.get('HINDSIGHT_AGENT_NAME','codex')+'-'+('compact' if source=='compact' else 'resume'))
            context=f"{instructions}\n{context}"
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            },
            sys.stdout,
        )
        sys.stdout.flush()
        _record_instruction(hook_input,'codex_session_start_stdout_written')
        if profile_included:
            record_output(CORE_REPORT, hook_input)
        return

    # Ordinary startup retains the existing health/pre-start behavior and does
    # not inject recovery context.
    try:
        api_url = get_api_url(config, debug_fn=_dbg, allow_daemon_start=False)
        HindsightClient(api_url, config.get("evolvingProfileApiToken"))
        debug_log(config, f"Evolving Profile server reachable at {api_url}")
    except (RuntimeError, ValueError) as e:
        debug_log(config, f"Evolving Profile not running, initiating background pre-start: {e}")
        try:
            prestart_daemon_background(config, debug_fn=_dbg)
        except Exception as error:
            debug_log(config, f"Pre-start unavailable: {type(error).__name__}")
    core = _core_context(config, hook_input)
    if core:
        json.dump(
            {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": core}},
            sys.stdout,
        )
        sys.stdout.flush()
        _record_instruction(hook_input,'codex_session_start_stdout_written')
        record_output(CORE_REPORT, hook_input)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[Evolving Profile] SessionStart error: {e}", file=sys.stderr)
        sys.exit(0)
