export type HostCapability={state?:string;evidence_kind?:string;stale?:boolean;observed_at?:string};
export type HostRow={host_id:string;labels?:Record<string,string>;status:string;
  installation:{state:string;candidates:Record<string,unknown>[]};configuration:{state:string;candidates:Record<string,unknown>[]};
  readiness:{capabilities:Record<string,HostCapability>;host_verified:boolean;capture_enabled:boolean};
  context?:Record<string,unknown>};
export type HostIntegrationReport={schema:string;hosts:HostRow[];environment?:Record<string,unknown>;
  configuration_write_enabled?:boolean;dependencies?:Record<string,unknown>};
export type HostAction={action:string;host_id?:string;locale?:string;plan_id?:string;expected_sha256?:string;confirm?:boolean;probe?:boolean};
const ACTIONS=new Set(['discover','doctor','guide','config-preview','config-apply','config-rollback','export-diagnostics']);
export function protocolProbeOutcome(value:Record<string,any>):{ok:boolean;errorCode:string|null;toolCount:number|null}{
  const probe=value?.protocol_probe;
  const ok=probe?.status==='protocol_verified';
  const errorCode=ok?null:typeof probe?.error_code==='string'&&/^[a-z0-9_]{1,100}$/.test(probe.error_code)?probe.error_code:'probe_unavailable';
  return {ok,errorCode,toolCount:ok&&Number.isInteger(probe?.listed_tools)&&probe.listed_tools>=0?probe.listed_tools:null};
}
export function capabilityState(capability?:HostCapability):string {
  if(capability?.stale)return 'stale';
  const state=capability?.state;
  if(state==='host_verified'&&capability?.evidence_kind!=='native_host')return capability?.evidence_kind==='isolated_probe'?'protocol_verified':'unknown';
  return ['unknown','unsupported','not_installed','documented','configured','protocol_verified','host_verified'].includes(state??'')?state!:'unknown';
}
export function validateHostAction(value:unknown):HostAction {
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('invalid_host_action');
  const r=value as Record<string,unknown>;
  if(Object.keys(r).some(k=>!['action','host_id','locale','plan_id','expected_sha256','confirm','probe'].includes(k))||!ACTIONS.has(String(r.action)))throw new Error('invalid_host_action');
  if(r.host_id!==undefined&&(typeof r.host_id!=='string'||!/^[a-z][a-z0-9_]{0,63}$/.test(r.host_id)))throw new Error('invalid_host_id');
  if(r.action!=='discover'&&!r.host_id)throw new Error('host_required');
  if(r.locale!==undefined&&(typeof r.locale!=='string'||!/^[A-Za-z-]{2,16}$/.test(r.locale)))throw new Error('invalid_locale');
  if(r.plan_id!==undefined&&(typeof r.plan_id!=='string'||!/^[a-f0-9]{32}$/.test(r.plan_id)))throw new Error('invalid_plan_id');
  if(r.expected_sha256!==undefined&&(typeof r.expected_sha256!=='string'||!/^([a-f0-9]{64}|absent)$/.test(r.expected_sha256)))throw new Error('invalid_revision');
  for(const key of ['confirm','probe'])if(r[key]!==undefined&&typeof r[key]!=='boolean')throw new Error('invalid_host_flag');
  if(r.probe&&r.action!=='doctor')throw new Error('invalid_probe_action');
  return r as HostAction;
}
