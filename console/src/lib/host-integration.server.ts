import {spawn} from 'node:child_process';
import path from 'node:path';
import {access} from 'node:fs/promises';
import {EP_STATE_ROOT} from './ep-state-paths';
import {validateHostAction} from './host-integration';

export async function runHostIntegration(action:string,input:object={}):Promise<Record<string,any>> {
  const value=validateHostAction({action,...input});
  const writable=process.env.EVOLVING_PROFILE_HOST_CONFIG_WRITE==='1';
  if(['config-apply','config-rollback'].includes(action)&&(!writable||!value.confirm||!value.plan_id||!value.expected_sha256))throw new Error('host_configuration_write_disabled');
  const source=process.env.EVOLVING_PROFILE_HOST_SOURCE_ROOT??path.resolve(process.cwd(),'..');
  const script=path.join(source,'scripts/ep-host.py');
  const localPython=path.join(source,'api/.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
  let python=process.env.EVOLVING_PROFILE_PYTHON??localPython;
  try{await access(python);}catch{python=process.platform==='win32'?'python':'python3';}
  const args=[script,action,'--state-root',EP_STATE_ROOT,'--json'];
  if(value.host_id)args.push('--host',value.host_id);
  if(value.locale)args.push('--locale',value.locale);
  if(value.probe)args.push('--probe');
  if(action==='config-preview'&&writable)args.push('--save-plan');
  if(['config-apply','config-rollback'].includes(action)){
    args.push('--confirm','--expected-sha256',value.expected_sha256!);
    args.push(action==='config-apply'?'--plan':'--receipt',path.join(EP_STATE_ROOT,'host-integrations',action==='config-apply'?'plans':'receipts',value.plan_id!+'.json'));
  }
  return await new Promise((resolve,reject)=>{
    const child=spawn(python,args,{shell:false,stdio:['ignore','pipe','pipe']});
    let out='',done=false;
    const finish=(error?:Error,data?:Record<string,any>)=>{if(done)return;done=true;clearTimeout(timer);error?reject(error):resolve({...data,configuration_write_enabled:writable});};
    const timer=setTimeout(()=>{child.kill('SIGTERM');finish(new Error('host_backend_timeout'));},20000);
    child.on('error',()=>finish(new Error('host_backend_unavailable')));
    child.stderr.on('data',()=>{});
    child.stdout.on('data',chunk=>{out+=chunk.toString('utf8');if(out.length>2*1024*1024){child.kill('SIGTERM');finish(new Error('host_output_budget_exceeded'));}});
    child.on('close',code=>{try{
      const data=JSON.parse(out.trim());
      if(!data||typeof data!=='object'||Array.isArray(data))throw new Error('host_invalid_response');
      if(code!==0)finish(new Error(/^[a-z0-9_]{1,100}$/.test(data.error_code??'')?data.error_code:'host_backend_failed'));
      else finish(undefined,data);
    }catch{finish(new Error('host_invalid_response'));}});
  });
}
