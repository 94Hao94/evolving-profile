import {expect,it} from 'vitest';
import {summarizeRuntimeLoad} from '@/lib/runtime-load-evidence';

const hash='a'.repeat(64),older='b'.repeat(64),now=Date.parse('2026-10-16T08:00:00Z');
const event=(digest=hash,at='2026-10-16T07:59:00Z')=>({adapter_build_sha256:digest,at,
  binding_state:'prompt_bound',session_id:'session',turn_id:'turn',tool_call_id:'call'});

it('does not equate installed code or saved settings with loaded MCP code',()=>{
 const out=summarizeRuntimeLoad({installed_mcp_sha256:hash,saved_config_sha256:hash,events:[]},now);
 expect(out.mcp_status).toBe('not_observed');expect(out.saved_config_status).toBe('saved');
 expect(out.configuration_applied).toBe('not_measured');
});
it('flags an actual old loaded reply even when disk has been upgraded',()=>{
 expect(summarizeRuntimeLoad({installed_mcp_sha256:hash,events:[event(older)]},now).mcp_status).toBe('reconnect_required');
 const mixed=summarizeRuntimeLoad({installed_mcp_sha256:hash,events:[event(older),{...event(),tool_call_id:'new'}]},now);
 expect(mixed.mcp_status).toBe('mixed_observations');expect(mixed.observed_reply_count).toBe(2);
});
it('keeps stale, anonymous, malformed and future replies out of a fresh-loaded claim',()=>{
 expect(summarizeRuntimeLoad({installed_mcp_sha256:hash,events:[event(hash,'2026-10-15T00:00:00Z')]},now).mcp_status).toBe('stale');
 for(const e of [{...event(),adapter_build_sha256:'v5.1'}, {...event(),binding_state:'unknown_check_id'},
   {...event(),tool_call_id:null},event(hash,'2026-10-17T00:00:00Z')])
   expect(summarizeRuntimeLoad({installed_mcp_sha256:hash,events:[e]},now).mcp_status).toBe('not_observed');
});
it('labels matching recent replies as observations, never all connections verified',()=>{
 const out=summarizeRuntimeLoad({installed_mcp_sha256:hash,events:[event(),event()]},now);
 expect(out.mcp_status).toBe('recent_reply_matches');expect(out.observed_reply_count).toBe(1);
 expect(out.all_connections_verified).toBe(false);
});
it('does not label a mutable disk build as the running server or browser build',()=>{
 const out=summarizeRuntimeLoad({console_disk_build_id:'disk-build-B',events:[]},now);
 expect(out.console_disk_build_id).toBe('disk-build-B');
 expect(out.console_running_build_status).toBe('not_measured');expect(out.console_client_build_status).toBe('not_measured');
 expect(out).not.toHaveProperty('console_build_id');
});
