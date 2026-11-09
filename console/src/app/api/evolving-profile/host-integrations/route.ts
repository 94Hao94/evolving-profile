import {runHostIntegration} from '@/lib/host-integration.server';
import {validateHostAction} from '@/lib/host-integration';
import {assertRecoveryOrigin} from '@/lib/memory-recovery-server';
export const dynamic='force-dynamic';
const headers={'Cache-Control':'no-store'};
export async function GET(){
  try{return Response.json(await runHostIntegration('discover'),{headers});}
  catch{return Response.json({error:'host_backend_unavailable'},{status:503,headers});}
}
export async function POST(request:Request){
  try{assertRecoveryOrigin(request);}catch{return Response.json({error:'host_origin_rejected'},{status:403,headers});}
  try{
    const reader=request.body?.getReader();if(!reader)throw new Error('invalid_host_action');
    let size=0;const chunks:Uint8Array[]=[];
    try{while(true){const row=await reader.read();if(row.done)break;size+=row.value.byteLength;if(size>8192){await reader.cancel();return Response.json({error:'host_input_too_large'},{status:413,headers});}chunks.push(row.value);}}finally{reader.releaseLock();}
    const {action,...input}=validateHostAction(JSON.parse(Buffer.concat(chunks).toString('utf8')));
    return Response.json(await runHostIntegration(action,input),{headers});
  }catch(error){
    const code=error instanceof Error&&/^[a-z0-9_]{1,100}$/.test(error.message)?error.message:'host_operation_failed';
    const status=code.includes('conflict')?409:code.includes('disabled')?403:code.startsWith('invalid')||code==='host_required'?400:502;
    return Response.json({error:code},{status,headers});
  }
}
