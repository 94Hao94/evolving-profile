/** Disk state, recent reply observations, and actual adoption are different evidence. */
const digest=(v:unknown):v is string=>typeof v==='string' && /^[0-9a-f]{64}$/.test(v);
export function summarizeRuntimeLoad(input:any,now=Date.now()) {
 const disk=digest(input?.installed_mcp_sha256)?input.installed_mcp_sha256:null;
 const events:any[]=[];const seen=new Set<string>();
 for(const e of Array.isArray(input?.events)?input.events:[]) {
  const at=Date.parse(e?.at);
  if(!digest(e?.adapter_build_sha256)||!Number.isFinite(at)||at>now+5000||e.binding_state!=='prompt_bound'
    ||!e.session_id||!e.turn_id||!e.tool_call_id||seen.has(e.tool_call_id))continue;
  seen.add(e.tool_call_id);events.push({at:e.at,adapter_build_sha256:e.adapter_build_sha256,tool_call_id:e.tool_call_id,
    source:e.source || 'mcp_reply_activity',process_id:e.adapter_process_id || null});
 }
 events.sort((a,b)=>Date.parse(b.at)-Date.parse(a.at));
 const recent=events.filter(e=>now-Date.parse(e.at)<=15*60*1000);
 const hashes=new Set(recent.map(e=>e.adapter_build_sha256));
 const mcp_status=!disk?'installed_unknown':!events.length?'not_observed':!recent.length?'stale'
   :hashes.size>1?'mixed_observations':hashes.has(disk)?'recent_reply_matches':'reconnect_required';
 return {saved_config_status:digest(input?.saved_config_sha256)?'saved':'unknown',
   saved_config_sha256:digest(input?.saved_config_sha256)?input.saved_config_sha256:null,
   saved_config_at:input?.saved_config_at || null,installed_mcp_sha256:disk,
   console_disk_build_id:typeof input?.console_disk_build_id==='string'?input.console_disk_build_id:null,
   console_running_build_status:'not_measured',console_client_build_status:'not_measured',
   mcp_status,observed_reply_count:recent.length,latest_observation_at:events[0]?.at || null,
   observations:events.slice(0,8),configuration_applied:'not_measured',all_connections_verified:false};
}
