import { readFile } from "node:fs/promises";
import { epStatePath } from "./ep-state-paths";
import { dataplaneBankUrl, getDataplaneHeaders } from "./evolving-client";
import type { BankAvailability, BankSelection } from "./bank-selection";

async function checkBank(bankId:string):Promise<BankAvailability> {
  try {
    // Unlike stats/list endpoints, profile distinguishes a missing bank from
    // a valid empty bank. This GET must never create a bank.
    const response=await fetch(dataplaneBankUrl(bankId,"/profile"),{
      headers:getDataplaneHeaders(), cache:"no-store", signal:AbortSignal.timeout(2500),
    });
    if(response.status===404) {
      const error=await response.json().catch(()=>null);
      // A reverse-proxy or wrong API prefix can also return 404. Only the
      // bank-specific dataplane contract is evidence of this bank's absence.
      return error?.detail===`Bank '${bankId}' not found` ? "missing" : "unavailable";
    }
    if(!response.ok) return "unavailable";
    const data=await response.json();
    return data?.bank_id===bankId ? "ready" : "unavailable";
  } catch { return "unavailable"; }
}

export async function resolveBankSelection(
  requested:string|null,
  readProfile:()=>Promise<string>=()=>readFile(epStatePath("codex.json"),"utf8"),
  check:(bankId:string)=>Promise<BankAvailability>=checkBank,
):Promise<BankSelection> {
  let bankId:string|null=null;
  let configStatus:"unconfigured"|"unavailable"="unconfigured";
  try {
    const profile=JSON.parse(await readProfile());
    if(!profile || typeof profile!=="object" || Array.isArray(profile)) configStatus="unavailable";
    else if(typeof profile.bankId==="string" && profile.bankId.trim()) bankId=profile.bankId;
    else if(profile.bankId!=null && profile.bankId!=="") configStatus="unavailable";
  } catch(error) {
    configStatus=(error as NodeJS.ErrnoException)?.code==="ENOENT"
      ? "unconfigured" : "unavailable";
  }
  // Request-local deduplication only. Never share selected banks between users.
  const checks=new Map<string,Promise<BankAvailability>>();
  const verify=(id:string)=>{
    if(!checks.has(id)) checks.set(id,check(id).catch(()=>"unavailable"));
    return checks.get(id)!;
  };
  const [primaryStatus,requestedStatus]=await Promise.all([
    bankId ? verify(bankId) : Promise.resolve(configStatus),
    requested ? verify(requested) : Promise.resolve(null),
  ]);
  const status=requested ? requestedStatus! : primaryStatus;
  return {
    schema:"ep.bank-selection.v1",requested_bank_id:requested,
    selected_bank_id:status==="ready" ? (requested||bankId) : null,
    status,primary:{bank_id:bankId,status:primaryStatus},
  };
}
