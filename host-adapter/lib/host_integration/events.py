"""Event shape normalization does not confer capture permission or success."""
import hashlib
import json
import uuid

EVENTS={'SessionStart':'session_started','UserPromptSubmit':'prompt_submitted',
        'PostToolUse':'tool_completed','Stop':'task_stopped','PreCompact':'before_compaction',
        'SessionEnd':'session_ended'}


def normalize_event(raw,profile,binding):
    name=raw.get('hook_event_name');kind=EVENTS.get(name)
    native=raw.get('message_id') or raw.get('tool_call_id') or raw.get('event_id')
    key=hashlib.sha256(json.dumps([binding.get('binding_key'),name,native or uuid.uuid4().hex]).encode()).hexdigest()
    outcome='cancelled' if raw.get('cancelled') else 'failed' if raw.get('error') or raw.get('failed') else 'not_verified'
    return {'schema':'ep.host-event.v1','host_id':profile['id'],'kind':kind,
            'event_key':key,'identity_origin':'host' if native else 'adapter_assigned',
            'status':'normalized' if kind else 'unknown_event','outcome':outcome,
            'binding':dict(binding),'capture_allowed':bool(kind and outcome!='cancelled' and
                binding.get('usable_for_capture') and profile.get('capture_enabled') is True and
                binding.get('source_verified') is True),'source_is_complete':False}
