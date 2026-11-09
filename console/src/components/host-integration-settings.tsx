'use client';
import {useEffect,useRef,useState} from 'react';
import {useLocale,useTranslations} from 'next-intl';
import {ActionButton} from '@/components/ui/action-button';
import {Button} from '@/components/ui/button';
import {Dialog,DialogContent,DialogTitle,DialogDescription} from '@/components/ui/dialog';
import {capabilityState,protocolProbeOutcome,type HostIntegrationReport,type HostRow} from '@/lib/host-integration';

export function HostIntegrationSettings({initialData}:{initialData?:HostIntegrationReport}){
  const t=useTranslations('hostIntegrations');const locale=useLocale();
  const [report,setReport]=useState<HostIntegrationReport|undefined>(initialData);
  const [error,setError]=useState('');const [loading,setLoading]=useState(!initialData);
  const [detail,setDetail]=useState<{host:string;value:Record<string,any>}|null>(null);
  const sequence=useRef(0);
  async function load(signal?:AbortSignal){
    setLoading(true);setError('');
    try{const response=await fetch('/api/evolving-profile/host-integrations',{cache:'no-store',signal});
      const value=await response.json();if(!response.ok||!Array.isArray(value.hosts))throw new Error(value.error??'host_invalid_response');setReport(value);
    }catch(e){if(signal?.aborted)return;setError(e instanceof Error?e.message:'host_backend_unavailable');throw e;}
    finally{if(!signal?.aborted)setLoading(false);}
  }
  useEffect(()=>{if(initialData)return;const controller=new AbortController();void load(controller.signal).catch(()=>{});return()=>controller.abort();},[initialData]);
  function label(row:HostRow){return row.labels?.[locale]??row.labels?.[locale.startsWith('zh')?'zh-CN':'en']??row.host_id;}
  function state(value:string){return t.has(`states.${value}`)?t(`states.${value}`):t('states.unknown');}
  async function action(row:HostRow,name:string){
    const ticket=++sequence.current;
    const response=await fetch('/api/evolving-profile/host-integrations',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({action:name,host_id:row.host_id,locale,...(name==='doctor'?{probe:true}:{})})});
    const value=await response.json();if(!response.ok)throw new Error(value.error??'host_operation_failed');
    if(ticket===sequence.current){setDetail({host:label(row),value});if(name==='doctor')void load().catch(()=>{});}
    if(name==='doctor'&&!protocolProbeOutcome(value).ok)throw new Error(`${t('probeFailed')}: ${protocolProbeOutcome(value).errorCode}`);
  }
  return <section className="space-y-5" aria-label={t('title')}>
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div className="space-y-1"><h2 className="text-xl font-semibold">{t('title')}</h2><p className="max-w-3xl text-sm text-muted-foreground">{t('intro')}</p></div>
      <ActionButton onAction={()=>load()} pendingLabel={t('checking')} successLabel={t('refreshed')} errorLabel={t('retry')}>{t('refresh')}</ActionButton>
    </header>
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">{t('preparation')}</div>
    {report?.environment&&<p className="text-sm text-muted-foreground">{t('environment')}: {String(report.environment.platform??'—')} · {String(report.environment.architecture??'—')} · {String(report.environment.mode??'—')}</p>}
    {loading&&!report&&<p role="status">{t('loading')}</p>}
    {error&&<p role="alert" className="rounded border border-red-300 p-3 text-sm text-red-700">{t('unavailable')} <code>{error}</code></p>}
    {report?.hosts.length===0&&<p>{t('empty')}</p>}
    <div className="grid gap-4 xl:grid-cols-2">
      {report?.hosts.map(row=><article key={row.host_id} className="min-w-0 rounded-xl border bg-card p-4 shadow-sm">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{label(row)}</h3>
          <span className="rounded-md border bg-muted px-2 py-1 text-xs">{state(row.installation.state)}</span></div>
        <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">{Object.entries(row.readiness.capabilities).map(([id,cap])=><div key={id} className="flex items-center justify-between gap-3 rounded-md bg-muted/40 px-2 py-1.5">
          <dt>{t.has(`capabilities.${id}`)?t(`capabilities.${id}`):id}</dt><dd className="whitespace-nowrap text-xs text-muted-foreground">{state(capabilityState(cap))}</dd>
        </div>)}</dl>
        <p className="my-3 text-xs text-muted-foreground">{t('captureOff')}</p>
        <div className="flex flex-wrap gap-2">
          <ActionButton variant="outline" size="sm" onAction={()=>action(row,'config-preview')} pendingLabel={t('generating')} successLabel={t('ready')} errorLabel={t('retry')}>{t('preview')}</ActionButton>
          <ActionButton variant="outline" size="sm" onAction={()=>action(row,'doctor')} pendingLabel={t('checking')} successLabel={t('checked')} errorLabel={t('retry')}>{t('probe')}</ActionButton>
          <ActionButton variant="outline" size="sm" onAction={()=>action(row,'guide')} pendingLabel={t('loading')} successLabel={t('ready')} errorLabel={t('retry')}>{t('guide')}</ActionButton>
          <Button variant="ghost" size="sm" onClick={()=>setDetail({host:label(row),value:row})}>{t('details')}</Button>
        </div>
      </article>)}
    </div>
    <Dialog open={detail!==null} onOpenChange={open=>{if(!open){sequence.current++;setDetail(null);}}}>
      <DialogContent closeLabel={t('close')} className="max-h-[85dvh] w-[calc(100%-2rem)] max-w-3xl overflow-y-auto rounded-xl border bg-background text-foreground">
        <DialogTitle>{detail?.host}</DialogTitle><DialogDescription>{t('detailBoundary')}</DialogDescription>
        {detail?.value.protocol_probe&&<p role="status" className={`rounded-lg border p-3 text-sm ${protocolProbeOutcome(detail.value).ok?'border-emerald-300 bg-emerald-50 text-emerald-950':'border-red-300 bg-red-50 text-red-950'}`}>
          {protocolProbeOutcome(detail.value).ok?t('probeSummary',{count:protocolProbeOutcome(detail.value).toolCount??t('states.unknown')}):`${t('probeFailed')}: ${protocolProbeOutcome(detail.value).errorCode}`}
        </p>}
        {detail?.value.text?<p className="whitespace-pre-wrap break-words text-sm leading-7">{String(detail.value.text)}</p>:
          <pre className="max-h-[50dvh] overflow-auto whitespace-pre-wrap break-all rounded-lg border bg-muted/40 p-3 text-xs leading-6">{JSON.stringify(detail?.value,null,2)}</pre>}
        <p className="text-sm text-muted-foreground">{t('writesDisabled')}</p>
        <div className="flex flex-wrap gap-2"><Button disabled title={t('writesDisabled')}>{t('apply')}</Button><Button variant="outline" disabled title={t('writesDisabled')}>{t('rollback')}</Button>
          <Button variant="outline" onClick={()=>{sequence.current++;setDetail(null);}}>{t('close')}</Button></div>
      </DialogContent>
    </Dialog>
  </section>;
}
