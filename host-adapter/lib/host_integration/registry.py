"""The shared host recipe catalog is documentation, not a live certification."""
import hashlib
import json
from pathlib import Path

CAPABILITIES = ('mcp_stdio','mcp_http','prompt_hook','stop_hook','tool_hook',
                'source_readback','automatic_capture','host_receive')
DEFAULT_REGISTRY = Path(__file__).resolve().parents[3] / 'config/host-integrations.v1.json'


def unique_object(pairs):
    result = {}
    for key,value in pairs:
        if key in result: raise ValueError('duplicate_json_key')
        result[key]=value
    return result


def load_registry(path=DEFAULT_REGISTRY):
    raw=Path(path).read_bytes()
    value=json.loads(raw,object_pairs_hook=unique_object)
    if not isinstance(value,dict) or value.get('schema')!='ep.host-registry.v1':
        raise ValueError('unsupported_host_registry')
    profiles=value.get('profiles')
    if not isinstance(profiles,list): raise ValueError('invalid_host_profiles')
    seen=set()
    for profile in profiles:
        if not isinstance(profile,dict) or not isinstance(profile.get('id'),str) or profile['id'] in seen:
            raise ValueError('invalid_host_profile_identity')
        seen.add(profile['id'])
        if not isinstance(profile.get('documented'),dict) or not isinstance(profile.get('config'),dict):
            raise ValueError('invalid_host_profile_contract')
        if any(v is not None and type(v) is not bool for v in profile['documented'].values()):
            raise ValueError('invalid_documented_capability')
    return {**value,'sha256':hashlib.sha256(raw).hexdigest()}


def get_profile(registry, host_id):
    for profile in registry['profiles']:
        if profile['id']==host_id:return profile
    raise ValueError('unknown_host_profile')
