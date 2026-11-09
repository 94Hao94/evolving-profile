#!/usr/bin/env python3
"""Claude Desktop (Cowork) <-> Evolving Profile hook bridge.  v1  (2026-10-23)

Why a separate file: hook_bridge.py (Claude Code CLI) is left untouched. This one fixes
protocol gaps found in the field:
  * output must be {"hookSpecificOutput": {"hookEventName": ..., "additionalContext": ...}}
    (the old bridge printed a top-level "additionalContext", which Claude ignores)
  * adapters read HINDSIGHT_AGENT_NAME (old bridge only set EVOLVING_PROFILE_AGENT_NAME)
  * covers PreToolUse / PreCompact too (the old one had only session/recall/retain/posttool)
  * writes a content-free diagnostic line per call (event, payload KEYS, duration, exit) to
    ~/.evolving-profile/claude-code/desktop-hook.log so "did the hook fire?" is answerable.

Contract: NEVER blocks Claude. Always exit 0. PreToolUse never emits a deny/ask decision.
Usage: hook_bridge_desktop.py <session|recall|pretool|posttool|precompact|retain>
"""
import json, os, re, subprocess, sys, time
from pathlib import Path

HOME = Path.home()
ADAPTERS = HOME / '.evolving-profile' / 'runtime' / 'host-adapter'
BASE = HOME / '.evolving-profile' / 'claude-code'
TRANSCRIPTS = BASE / 'transcripts'
LOG = BASE / 'desktop-hook.log'
AGENT = 'claude-desktop'   # default; main() replaces it with detect_host()


def detect_host(env=None):
    """Which Claude host is calling? Order: explicit EP_HOST override, then Claude Code's own markers.
    Known: Claude Desktop/Cowork (CLAUDE_CODE_IS_COWORK=1 or entrypoint local-agent/claude-desktop), Claude CLI (entrypoint cli).
    Anything else (sdk, ide, future values) -> generic 'claude-code'; never raises. The raw entrypoint is logged so new ones are visible."""
    e = os.environ if env is None else env
    forced = (e.get('EP_HOST') or '').strip().lower()
    if forced and all(c.isalnum() or c in '-_' for c in forced):
        return forced[:40]
    entry = (e.get('CLAUDE_CODE_ENTRYPOINT') or '').strip().lower()
    cowork = (e.get('CLAUDE_CODE_IS_COWORK') or '').strip().lower() in ('1', 'true', 'yes')
    if cowork or entry in ('local-agent', 'claude-desktop', 'desktop'):
        return 'claude-desktop'
    if entry == 'cli':
        return 'claude-cli'
    return 'claude-code'

INSTR_RE = re.compile(r'<evolving_profile_memory_use_instruction\b([^>]*)>.*?</evolving_profile_memory_use_instruction>', re.S)


def _marker(session_id):
    safe = ''.join(c for c in session_id if c.isalnum() or c in '-_')[:120] or 'unknown'
    return BASE / 'instruction-seen' / safe


def dedupe_instruction(event, session_id, context):
    """SessionStart delivers the full instruction and leaves a marker; later events in the same session get a stub.
    Returns (context, saved_chars)."""
    if os.environ.get('EP_FULL_INSTRUCTION') == '1' or not context:
        return context, 0
    try:
        m = _marker(session_id)
        if event == 'session':
            if INSTR_RE.search(context):
                m.parent.mkdir(parents=True, exist_ok=True)
                m.write_text(str(time.time()))
            return context, 0
        if not m.exists():
            return context, 0
        def stub(x):
            attrs = ' '.join(re.findall(r'\b(?:version|sha256)="[^"]*"', x.group(1)))
            return f'<evolving_profile_memory_use_instruction {attrs} deduped="full text delivered at SessionStart of this session"/>'
        new = INSTR_RE.sub(stub, context)
        return new, len(context) - len(new)
    except Exception:
        return context, 0


EVENTS = {  # event -> (adapter script, timeout seconds, claude hookEventName, may inject context)
    'session':    ('session_start.py',  8,  'SessionStart',     True),
    'recall':     ('recall.py',         60, 'UserPromptSubmit', True),
    'pretool':    ('pre_tool_use.py',   4,  'PreToolUse',       True),
    'posttool':   ('post_tool_use.py',  15, 'PostToolUse',      False),
    'precompact': ('pre_compact.py',    6,  'PreCompact',       False),
    'retain':     ('retain.py',         40, 'Stop',             False),
}


def log(event, **kw):
    try:
        if LOG.exists() and LOG.stat().st_size > 2_000_000:
            LOG.replace(LOG.with_name(LOG.name + '.1'))
        rec = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'event': event, **kw}
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        pass


def text_of(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [text_of(x) for x in value]
        return '\n'.join(p for p in parts if p).strip()
    if isinstance(value, dict):
        t = value.get('type')
        if t in ('tool_use', 'tool_result', 'thinking', 'image'):
            return ''  # keep retained transcript to human-visible dialogue
        if 'text' in value:
            return str(value.get('text') or '').strip()
        if 'content' in value:
            return text_of(value['content'])
    return ''


def normalize_transcript(source, session_id):
    """Claude JSONL -> [{'role','content'}] lines. Returns (target_path, n_records, source_state)."""
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    safe = ''.join(c for c in session_id if c.isalnum() or c in '-_')[:120] or 'unknown'
    target = TRANSCRIPTS / f'{safe}.jsonl'
    if not source:
        return str(target), 0, 'no_transcript_path'
    try:
        lines = Path(source).read_text(encoding='utf-8').splitlines()
    except OSError as e:
        return str(target), 0, f'unreadable:{type(e).__name__}'
    records, seen = [], set()
    for raw in lines:
        try:
            entry = json.loads(raw)
        except Exception:
            continue
        msg = entry.get('message') if isinstance(entry.get('message'), dict) else None
        role = entry.get('role') or (msg or {}).get('role') or entry.get('type')
        if role not in ('user', 'assistant'):
            continue
        if entry.get('isSidechain') or entry.get('isMeta'):
            continue
        content = text_of((msg or {}).get('content') if msg is not None else entry.get('content'))
        if not content or content.startswith('<system-reminder>') or content.startswith('<command-'):
            continue
        key = (role, content)
        if key in seen:
            continue
        seen.add(key)
        records.append({'role': role, 'content': content})
    # never clobber a good earlier snapshot with an empty one
    if records or not target.exists():
        target.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in records), encoding='utf-8')
    return str(target), len(records), 'ok' if records else 'parsed_but_empty'


def run_adapter(script, payload, timeout):
    env = os.environ.copy()
    env['HINDSIGHT_AGENT_NAME'] = AGENT
    env['EVOLVING_PROFILE_AGENT_NAME'] = AGENT
    py = HOME / '.evolving-profile' / 'runtime' / 'python-3.11' / 'bin' / 'python'
    p = subprocess.run([str(py if py.exists() else sys.executable), str(ADAPTERS / script)],
                       input=json.dumps(payload, ensure_ascii=False), text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=env)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else ''
    if event not in EVENTS:
        log(event or 'none', error='unknown_event')
        return
    script, timeout, hook_name, may_inject = EVENTS[event]
    t0 = time.time()
    global AGENT
    AGENT = detect_host()
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            incoming = {}
    except Exception:
        incoming = {}
    session_id = str(incoming.get('session_id') or 'unknown')
    payload = dict(incoming)
    payload['session_id'] = session_id
    payload.setdefault('hook_event_name', hook_name)
    tstate, nrec = 'n/a', None
    if event in ('session', 'recall', 'retain', 'precompact', 'posttool'):
        path, nrec, tstate = normalize_transcript(incoming.get('transcript_path') or '', session_id)
        payload['transcript_path'] = path
    if 'prompt' in payload and 'user_prompt' not in payload:
        payload['user_prompt'] = payload['prompt']

    rc, out, err = run_adapter(script, payload, timeout)
    extra = {}
    if event == 'retain':  # also emit a Codex-format rollout so the Scenario Summary pipeline can see desktop chats
        try:
            sys.path.insert(0, str(BASE))
            import desktop_rollout
            extra = desktop_rollout.write_rollout(session_id, incoming.get('transcript_path'), incoming.get('cwd'), host=AGENT)
        except Exception as exc:
            extra = {'rollout': f'bridge_error:{type(exc).__name__}'}
    if event in ('session', 'recall', 'retain'):  # write deferred updates whose rollout has been quiet long enough
        try:
            sys.path.insert(0, str(BASE))
            import desktop_rollout
            n = desktop_rollout.flush_pending()
            if n:
                extra = {**extra, 'rollout_flushed': n}
        except Exception as exc:
            extra = {**extra, 'flush_error': type(exc).__name__}
    context, decision_seen = '', False
    if out:
        try:
            obj = json.loads(out)
            hso = obj.get('hookSpecificOutput') or {}
            context = hso.get('additionalContext') or obj.get('additionalContext') or ''
            decision_seen = bool(hso.get('permissionDecision') or obj.get('decision'))
        except Exception:
            context = out if may_inject else ''  # plain stdout is accepted as context by Claude hooks
    saved = 0
    if may_inject and context:
        context, saved = dedupe_instruction(event, session_id, context)
    if may_inject and context:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': hook_name, 'additionalContext': context}}, ensure_ascii=False))
    log(event, host=AGENT, entrypoint=os.environ.get('CLAUDE_CODE_ENTRYPOINT', ''), session=session_id[:12], sid_full=session_id, transcript_stem=Path(incoming.get('transcript_path') or '').stem, payload_keys=sorted(incoming.keys()), transcript=tstate, transcript_records=nrec,
        adapter_rc=rc, out_chars=len(out), injected_chars=len(context) if may_inject else 0, dedup_saved=saved,
        adapter_wanted_decision=decision_seen, stderr_head=(err[:160] if rc != 0 else ''), ms=round((time.time() - t0) * 1000), **extra)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:  # memory degradation must never block Claude
        log(sys.argv[1] if len(sys.argv) > 1 else 'none', error=f'{type(exc).__name__}: {str(exc)[:200]}')
    sys.exit(0)
