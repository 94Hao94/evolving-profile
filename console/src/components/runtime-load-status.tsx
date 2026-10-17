"use client";
import {useLocale,useTranslations} from 'next-intl';

export function RuntimeLoadStatus({data}:{data:any}){
 const t=useTranslations('runtimeLoad'),locale=useLocale();
 const status=['installed_unknown','not_observed','stale','mixed_observations','recent_reply_matches','reconnect_required'].includes(data?.mcp_status)?data.mcp_status:'not_observed';
 return <section className="rounded-lg border bg-background p-4 text-foreground" data-testid="runtime-load-status">
  <h3 className="font-semibold">{t('title')}</h3><p className="mt-1 text-xs text-muted-foreground">{t('boundary')}</p>
  {!['en','zh-CN','zh-TW','yue-Hant'].includes(locale)?<p className="text-xs text-muted-foreground">{t('fallback')}</p>:null}
  <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
   <article className="rounded border p-3"><h4 className="text-sm font-medium">{t('saved')}</h4>
    <p className="mt-2 text-xs">{t(data?.saved_config_status==='saved'?'saved_yes':'unknown')}</p>
    <code className="break-all text-[10px]" title={data?.saved_config_sha256??''}>{data?.saved_config_sha256?.slice(0,12)??'—'}</code>
    <p className="break-all text-[10px] text-muted-foreground">{data?.saved_config_at??'—'}</p></article>
   <article className="rounded border p-3"><h4 className="text-sm font-medium">{t('installed')}</h4>
    <p className="mt-2 text-xs">{t(data?.installed_mcp_sha256?'installed_yes':'unknown')}</p>
    <code className="break-all text-[10px]" title={data?.installed_mcp_sha256??''}>{data?.installed_mcp_sha256?.slice(0,12)??'—'}</code></article>
   <article className="rounded border p-3"><h4 className="text-sm font-medium">{t('web')}</h4>
    <code className="mt-2 block break-all text-xs">{data?.console_disk_build_id??t('unknown')}</code><p className="mt-1 text-[10px] text-muted-foreground">{t('webBoundary')}</p></article>
   <article className="rounded border p-3"><h4 className="text-sm font-medium">{t('observed')}</h4>
    <p className="mt-2 text-xs" role="status">{t(status)}</p><p className="text-[10px]">{t('replyCount',{count:data?.observed_reply_count??0})}</p>
    <p className="break-all text-[10px] text-muted-foreground">{data?.latest_observation_at??'—'}</p></article>
  </div>
  <details className="mt-3 text-xs"><summary className="cursor-pointer">{t('details')}</summary>
   <div className="mt-2 max-h-48 space-y-2 overflow-auto [scrollbar-gutter:stable]">{(data?.observations??[]).map((r:any)=><div key={r.tool_call_id} className="rounded border p-2">
    <p>{r.at}</p><code className="break-all">{r.adapter_build_sha256}</code><p className="break-all">{r.tool_call_id}</p>
   </div>)}</div></details>
 </section>;
}
