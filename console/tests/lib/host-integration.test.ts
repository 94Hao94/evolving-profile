import { describe,it,expect } from 'vitest';

describe('host readiness projection',()=>{
  it('unknown is not zero or successful',async()=>{
    const {capabilityState}=await import('../../src/lib/host-integration');
    expect(capabilityState(undefined)).toBe('unknown');
    expect(capabilityState({state:'protocol_verified',evidence_kind:'isolated_probe'})).toBe('protocol_verified');
    expect(capabilityState({state:'host_verified',evidence_kind:'isolated_probe'})).toBe('protocol_verified');
  });
  it('rejects executable and target injection in browser action',async()=>{
    const {validateHostAction}=await import('../../src/lib/host-integration');
    expect(()=>validateHostAction({action:'doctor',host_id:'workbuddy',command:'evil'})).toThrow();
    expect(()=>validateHostAction({action:'config-preview',host_id:'workbuddy',target:'/private/file'})).toThrow();
    expect(validateHostAction({action:'guide',host_id:'doubao_work',locale:'zh-CN'})).toEqual({action:'guide',host_id:'doubao_work',locale:'zh-CN'});
  });
  it('an HTTP200 diagnostic containing a failed probe is not success feedback',async()=>{
    const {protocolProbeOutcome}=await import('../../src/lib/host-integration');
    expect(protocolProbeOutcome({protocol_probe:{status:'failed',error_code:'timeout'}})).toEqual({ok:false,errorCode:'timeout',toolCount:null});
    expect(protocolProbeOutcome({})).toEqual({ok:false,errorCode:'probe_unavailable',toolCount:null});
  });
  it('verified probe preserves actual zero count without certifying the host',async()=>{
    const {protocolProbeOutcome}=await import('../../src/lib/host-integration');
    expect(protocolProbeOutcome({protocol_probe:{status:'protocol_verified',listed_tools:0}})).toEqual({ok:true,errorCode:null,toolCount:0});
  });
});
