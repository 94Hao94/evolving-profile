import {readScenarioSnapshot,ScenarioRequestError} from "@/lib/scenario-data";
import {epStatePath,EP_RUNTIME_PYTHON,EP_STATE_ROOT} from "@/lib/ep-state-paths";
import {execFile} from "node:child_process";
import {promisify} from "node:util";

export async function GET(request:Request){
 try{
  const params=new URL(request.url).searchParams,sid=params.get("sessionId")??"",view=params.get("view")??"overview",cursor=params.get("cursor");
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(sid) || !["overview","requirements","relations","source"].includes(view) || (cursor?.length??0)>4096)throw new ScenarioRequestError(400,"coverage_request_invalid");
  const snapshot=await readScenarioSnapshot(params.get("bankId"));
  const row=(snapshot.index.sessions??[]).find((r:Record<string,unknown>)=>r.session_id===sid);
  if(!row || row.bank_id!==snapshot.bankId || String(row.status).endsWith("_protected"))throw new ScenarioRequestError(403,"coverage_scope_unverified");
  const args=[epStatePath("runtime/host-adapter/context-coverage-read.py"),"--state-root",EP_STATE_ROOT,"--session-id",sid,"--view",view,"--bank-id",snapshot.bankId,"--project-key",String(row.project_key??"")];
  if(cursor)args.push("--cursor",cursor);
  if(view==="source"){
   const requirement=params.get("requirementId")??"";
   if(!/^[0-9a-f]{64}$/.test(requirement))throw new ScenarioRequestError(400,"coverage_requirement_invalid");
   args.push("--requirement-id",requirement);
  }
  const {stdout}=await promisify(execFile)(EP_RUNTIME_PYTHON,args,{timeout:8000,maxBuffer:256*1024});
  return Response.json(JSON.parse(stdout),{headers:{"cache-control":"no-store"}});
 }catch(error){
  return Response.json({status:"unavailable",error:error instanceof ScenarioRequestError?error.message:"coverage_read_unavailable"},{status:error instanceof ScenarioRequestError?error.status:503,headers:{"cache-control":"no-store"}});
 }
}
