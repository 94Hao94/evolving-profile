import { epStatePath } from '@/lib/ep-state-paths';
import { readSharedLayout, saveSharedLayout } from '@/lib/topology-layout-store.server';
import { assertRecoveryOrigin } from '@/lib/memory-recovery-server';

export const dynamic='force-dynamic';
const headers={'Cache-Control':'no-store'};
const location=()=>epStatePath('config/topology-layout.json');
export async function GET() {
  try {return Response.json(await readSharedLayout(location()),{headers});}
  catch {return Response.json({error:'layout_unreadable'},{status:503,headers});}
}
export async function PUT(request:Request) {
  // The existing app guard checks the browser Host authority as well as the
  // internally normalized Next URL; localhost and127.0.0.1 are not conflated.
  try{assertRecoveryOrigin(request);}catch{return Response.json({error:'layout_origin_rejected'},{status:403,headers});}
  try {
    const reader=request.body?.getReader();if(!reader)throw new Error('invalid_layout');
    const chunks:Uint8Array[]=[];let size=0;
    try {while(true){const part=await reader.read();if(part.done)break;size+=part.value.byteLength;if(size>65536){await reader.cancel();return Response.json({error:'layout_too_large'},{status:413,headers});}chunks.push(part.value);}}finally{reader.releaseLock();}
    const body=Buffer.concat(chunks);const input=JSON.parse(body.toString('utf8'));
    return Response.json(await saveSharedLayout(location(),input),{headers});
  } catch(error) {
    const message=error instanceof Error?error.message:'layout_save_failed';
    const code=message==='layout_revision_conflict'||message==='layout_save_busy'?409:message==='layout_unreadable'?503:message.startsWith('invalid_')||message==='layout_canvas_mismatch'||error instanceof SyntaxError?400:500;
    return Response.json({error:code===500?'layout_save_failed':message},{status:code,headers});
  }
}
