import registry from "../../../config/scenario-coverage-contract.json";

export const coverageRegistry=registry;
export type CoverageSettings={mode:string;limits:Record<string,number>;model_trial:boolean;review_protocol:string};
export function coverageDefaults(protocol:string):Record<string,number>{
 if(!Object.hasOwn(registry.review_protocols,protocol))throw new Error("coverage_protocol_invalid");
 const overrides=(registry.review_protocols as Record<string,{defaults?:Record<string,number>}>)[protocol].defaults??{};
 return {...registry.defaults,...overrides};
}
export function normalizeCoverageSettings(value:unknown={}):CoverageSettings {
 if(!value || typeof value!=="object" || Array.isArray(value))throw new Error("coverage_settings_invalid");
 const v=value as Record<string,unknown>;
 if(Object.keys(v).some(k=>!["mode","limits","model_trial","review_protocol"].includes(k)))throw new Error("coverage_settings_invalid");
 const mode=v.mode??registry.mode,trial=v.model_trial??false;
 if(typeof mode!=="string" || !registry.modes.includes(mode) || typeof trial!=="boolean")throw new Error("coverage_settings_invalid");
 const protocol=v.review_protocol??registry.default_review_protocol;
 if(typeof protocol!=="string" || !Object.hasOwn(registry.review_protocols,protocol) || (protocol==="hierarchical_review.v1" && mode==="enforced"))throw new Error("coverage_protocol_invalid");
 const limits=v.limits??{};
 const defaults=coverageDefaults(protocol);
 if(!limits || typeof limits!=="object" || Array.isArray(limits))throw new Error("coverage_limits_invalid");
 for(const [k,n] of Object.entries(limits)){
   if(!registry.editable_limits.includes(k) || !Number.isSafeInteger(n) || Number(n)<((registry.minimum_limits as Record<string,number>)[k]??1) || Number(n)>defaults[k])throw new Error("coverage_limits_invalid");
 }
 return {mode,limits:{...limits as Record<string,number>},model_trial:trial,review_protocol:protocol};
}
export function switchCoverageProtocol(value:unknown,protocol:string):CoverageSettings{
 const current=normalizeCoverageSettings(value),defaults=coverageDefaults(protocol);
 const limits=Object.fromEntries(Object.entries(current.limits).filter(([key,n])=>n<=defaults[key]));
 return normalizeCoverageSettings({...current,review_protocol:protocol,limits,mode:protocol==="hierarchical_review.v1"&&current.mode==="enforced"?"source_shadow":current.mode});
}
export function coverageSummary(value:Record<string,unknown>|null|undefined){
 return {structureComplete:value?.source_manifest_complete===true,
   semanticAccepted:value?.status==="accepted" && value?.semantic_review_status==="automated_declared_scope_accepted",
   requirements:Number.isSafeInteger(value?.requirement_count) ? Number(value?.requirement_count):null,
   sourceReadback:false,hostDelivery:"not_measured"};
}
