"use client";
import {useEffect,useState} from "react";
import {useLocale,useTranslations} from "next-intl";
import {coverageSummary,coverageRegistry} from "@/lib/scenario-coverage";

export function RelationRows({rows,onRead}:{rows:any[];onRead:(id:string)=>void}){
 const t=useTranslations("scenarioCoverage"),h=useTranslations("hierarchicalReview");
 return <div className="max-h-72 space-y-2 overflow-auto rounded border p-2">{rows.map((r:any,index:number)=>{
  const ids=Array.isArray(r.atom_ids)?r.atom_ids:[r.from];
  return <article key={`${index}:${r.detail_offset??0}`}><strong>{r.type==="obligation"?h("obligation"):t(r.type==="supersedes"?"relation_supersedes":"relation_conflicts")}</strong><p data-i18n-ignore="true" className="whitespace-pre-wrap break-words">{r.evidence_quote}</p><div className="flex flex-wrap gap-2">{ids.map((id:unknown,n:number)=><button key={`${String(id)}:${n}`} type="button" disabled={typeof id!=="string"||!/^[0-9a-f]{64}$/.test(id)} className="rounded border px-2 py-1 disabled:opacity-40" onClick={()=>{if(typeof id==="string")onRead(id);}}>{t("readOriginal")} {n+1}</button>)}</div></article>;
 })}</div>;
}

export function CoverageStatusCard({data}:{data:Record<string,any>}){
 const t=useTranslations("scenarioCoverage"),h=useTranslations("hierarchicalReview"),locale=useLocale(),summary=coverageSummary(data);
 const hierarchy=data.coverage_contract==="hierarchical_review.v1";
 const legacyCompatibility=hierarchy&&data.coverage?.target_complete===true&&data.coverage?.scope_axes_complete!==true;
 const hierarchicalStates=coverageRegistry.review_protocols["hierarchical_review.v1"].statuses;
 const status=coverageRegistry.statuses.includes(data.status)?data.status:"unavailable";
 return <section className="space-y-2 rounded-lg border border-sky-200 bg-background p-3 text-foreground" data-testid="scenario-coverage-status">
  <h4 className="font-semibold">{t("title")}</h4>
  {locale!=="en" && locale!=="zh-CN"?<p>{t("fallback")}</p>:null}
  <p>{legacyCompatibility?h("legacyCompatibility"):hierarchy&&hierarchicalStates.includes(data.status)&&!["budget_paused","unavailable"].includes(data.status)?h(`status_${data.status}`):t(`status_${status}`)}</p>
  {hierarchy?<div className="space-y-1 rounded border bg-background p-2 text-sm"><strong>{h("nonExhaustive")}</strong>
   <p>{h("attribution")}: {h(data.coverage?.attribution_review==="complete"?"reviewed":data.coverage?.attribution_review==null||data.coverage?.attribution_review==="stale"?"unknown":"partial")}</p>
   <p>{h("scope")}: {h(data.coverage?.scope_review==="resolved"?"scopeReviewed":data.coverage?.scope_review==="unresolved"?"partial":"unknown")}</p>
   <p>{h("outcomeNotVerified")}</p>
   <p>{h("contextPages")}: {data.context_original_pages_materialized??h("unknown")}</p>
   {data.processing_diagnostics?<div className="space-y-1 text-xs">
    <p>{h("formatReselections")}: {data.processing_diagnostics.format_reselections??h("unknown")} · {h("repairCalls")}: {data.processing_diagnostics.repair_model_calls??h("unknown")}</p>
    <p>{h("wireCapacity")}: {data.processing_diagnostics.max_extract_wire_bytes??h("unknown")} B · {h("transportWindows")}: {data.processing_diagnostics.transport_windows??h("unknown")}</p>
    {data.processing_diagnostics.source_scope_reduced===false?<p>{h("sourceNotReduced")}</p>:null}
   </div>:null}
   <p>{h("intent")}: {h(data.coverage?.intent_review==="complete"?"reviewed":"partial")}</p>
   <p>{h("discovery")}: {h(data.coverage?.discovery_procedure_coverage==="complete"?"reviewed":"partial")}</p>
   <p>{h("unresolved")}: {data.unresolved_count??h("unknown")} · {h("unread")}: {data.unread_count??h("unknown")}</p>
   <p className="text-amber-700 dark:text-amber-300">{h("noGuidance")}</p>
  </div>:null}
  <dl className="grid grid-cols-2 gap-2"><dt>{t("structure")}</dt><dd>{t(summary.structureComplete?"complete":"incomplete")}</dd>
   <dt>{hierarchy?h("target"):t("semantics")}</dt><dd>{hierarchy?h(legacyCompatibility?"legacyCompatibility":data.coverage?.target_complete===true?"reviewed":"partial"):t(summary.semanticAccepted?"reviewed":"notReviewed")}</dd>
   <dt>{t("entryCount")}</dt><dd>{summary.requirements??"—"}</dd>
   <dt>{t("rawSource")}</dt><dd>{t(data.source_readback===true?"readBack":"notRead")}</dd>
   <dt>{t("watermark")}</dt><dd>{data.watermark?.logical_offset??data.logical_offset??"—"}</dd>
   <dt>{t("segments")}</dt><dd>{data.partition_count??"—"}</dd>
   <dt>{t("cost")}</dt><dd>{data.budget?`${data.budget.requests_used??"—"} / ${data.budget.max_requests??"—"} · ${data.budget.charged_tokens??"—"}`:t(data.model_calls===0?"zero":"unknown")}</dd>
   <dt>{t("unknownUsage")}</dt><dd>{data.budget?.unknown_usage_requests??(data.model_calls===0?0:"—")}</dd>
   <dt>{t("reserved")}</dt><dd>{data.budget?.reserved_requests??(data.model_calls===0?0:"—")}</dd>
   <dt>{t("cache")}</dt><dd>{data.reused_review_requests??(data.model_calls===0?0:"—")}</dd>
   {data.incremental?<><dt>{t("sourceReuse")}</dt><dd>{data.incremental.reused_source_units??"—"}</dd><dt>{t("draftReuse")}</dt><dd>{data.incremental.reused_partition_drafts??"—"}</dd></>:null}
  </dl>
  {hierarchy&&data.coverage?.groups&&typeof data.coverage.groups==="object"?<details className="rounded border p-2"><summary className="cursor-pointer text-sm">{h("groups")} · {Object.keys(data.coverage.groups).length}</summary><div className="mt-2 max-h-56 space-y-2 overflow-y-auto [scrollbar-gutter:stable]">{Object.entries(data.coverage.groups).map(([id,value]:[string,any])=><p key={id} className="text-xs"><code data-i18n-ignore="true">{id.slice(0,12)}</code> · {h(legacyCompatibility&&value?.status==="scope_reviewed"?"legacyCompatibility":["scope_reviewed","intent_gap","relation_pending","stale"].includes(value?.status)?`status_${value.status}`:"unknown")}</p>)}</div></details>:null}
  <p className="text-amber-700 dark:text-amber-300">{t("boundary")}</p>
  {data.has_unread_requirements?<p>{t("unread")}</p>:null}
  {data.scope?<p>{t("scopeBoundary")} <code data-i18n-ignore="true">{data.scope.project_key??"—"}</code></p>:null}
  {(["current_conditions","historical_conditions","unresolved_conditions"] as const).map(key=>data[key]?.length?<div key={key}><strong>{t(key)}</strong>{data[key].map((r:any)=><p key={r.intent_id} className="whitespace-pre-wrap break-words" data-i18n-ignore="true">{r.source_quote}</p>)}</div>:null)}
  {data.reason==="review_protocol_changed"?<p className="text-sm text-amber-700 dark:text-amber-300">{t("protocolChanged")}</p>:data.reason?<code className="block break-all text-[10px]" data-i18n-ignore="true">{data.reason}</code>:null}
 </section>;
}

export function ScenarioCoverageDetails({sessionId,bankId}:{sessionId:string;bankId:string}){
 const t=useTranslations("scenarioCoverage"),h=useTranslations("hierarchicalReview");
 const [view,setView]=useState("overview"),[cursor,setCursor]=useState<string|null>(null),[retry,setRetry]=useState(0),[requirement,setRequirement]=useState<string|null>(null);
 const [state,setState]=useState<{key:string;data?:Record<string,any>;error?:boolean}>({key:""});
 const key=JSON.stringify([sessionId,bankId,view,cursor,retry,requirement]);
 useEffect(()=>{
  const controller=new AbortController();let active=true;
  const params=new URLSearchParams({sessionId,bankId,view});if(cursor)params.set("cursor",cursor);
  if(requirement)params.set("requirementId",requirement);
  void fetch(`/api/evolving-profile/scenario/coverage?${params}`,{cache:"no-store",signal:controller.signal}).then(async r=>{
   const data=await r.json();if(!r.ok)throw new Error();if(active)setState({key,data});
  }).catch(()=>{if(active)setState({key,error:true});});
  return()=>{active=false;controller.abort();};
 },[key,sessionId,bankId,view,cursor,retry,requirement]);
 const data=state.key===key?state.data:undefined,error=state.key===key && state.error;
 return <div className="space-y-2">
  {!data && !error?<p role="status">{t("loading")}</p>:null}
  {error?<div role="alert">{t("error")} <button type="button" className="underline" onClick={()=>setRetry(r=>r+1)}>{t("retry")}</button></div>:null}
  {data?<><CoverageStatusCard data={data}/>
   <div className="flex gap-2">{["overview","requirements","relations"].map(v=><button key={v} type="button" className="rounded border px-2 py-1" aria-pressed={view===v} onClick={()=>{setView(v);setCursor(null);}}>{t(v)}</button>)}</div>
   {data.requirements?.length?<div className="max-h-72 overflow-y-auto rounded border bg-background p-2 [scrollbar-gutter:stable]">{data.requirements.map((r:any)=><article key={`${r.requirement_id}:${r.text_offset}`} className="mb-3 whitespace-pre-wrap break-words">
    <code data-i18n-ignore="true">{r.requirement_id.slice(0,12)} · {r.text_offset}/{r.text_total_chars}</code><p>{t(`requirement_${["covered","unresolved","omitted","superseded","answered","non_substantive"].includes(r.status)?r.status:"unresolved"}`)} · {r.intent_count==null?t("unknown"):t("intentCount",{count:r.intent_count})}</p><p data-i18n-ignore="true">{r.text}</p>
    {r.semantic_state?<p className="text-xs">{h("proposedState")}: {h(["current","historical","unresolved","reported"].includes(r.semantic_state.state)?`state_${r.semantic_state.state}`:"unknown")} · {h(r.semantic_state.verification==="source_readback_supported"?"sourceSupported":"proposalOnly")}</p>:null}
    {r.intents?.map((i:any)=><div key={i.intent_id} className="mt-1 border-l-2 pl-2"><small>{t(`intent_${["request","constraint","correction","question","confirmation"].includes(i.kind)?i.kind:"unknown"}`)} · {t(`requirement_${["covered","unresolved","omitted","superseded","answered","non_substantive"].includes(i.status)?i.status:"unresolved"}`)}</small><p data-i18n-ignore="true">{i.source_quote}</p></div>)}
    <button type="button" className="mt-2 rounded border px-2 py-1" onClick={()=>{setRequirement(r.requirement_id);setView("source");setCursor(null);}}>{t("readOriginal")}</button>
    <details><summary>{t("locator")}</summary><code className="break-all" data-i18n-ignore="true">{r.source_locator?.scenario_id}</code></details>
   </article>)}</div>:null}
   {view==="relations"?<RelationRows rows={data.relations??[]} onRead={id=>{setRequirement(id);setView("source");setCursor(null);}}/>:null}
   {view==="source"?<div className="max-h-72 overflow-auto rounded border bg-background p-2"><p>{t(data.source_readback===true?"readBack":"notRead")}</p><pre className="whitespace-pre-wrap break-words" data-i18n-ignore="true">{data.raw_source?.text??""}</pre></div>:null}
   {data.coverage_cursor?<button type="button" className="rounded border px-2 py-1" onClick={()=>setCursor(data.coverage_cursor)}>{t("next")}</button>:null}
  </>:null}
 </div>;
}
