"use client";
import {useTranslations,useLocale} from "next-intl";
import {coverageRegistry,normalizeCoverageSettings,coverageDefaults,switchCoverageProtocol} from "@/lib/scenario-coverage";
import {ActionButton} from "@/components/ui/action-button";

export function ScenarioCoverageSettings({value,onChange,onSave}:{value:unknown;onChange:(v:unknown)=>void;onSave:()=>Promise<unknown>}){
 const t=useTranslations("scenarioCoverage"),h=useTranslations("hierarchicalReview"),locale=useLocale(),settings=normalizeCoverageSettings(value??{});
 const d=coverageDefaults(settings.review_protocol);
 return <section className="space-y-3 rounded-lg border bg-background p-4" data-testid="scenario-coverage-settings">
  <h3 className="font-semibold">{t("title")}</h3><p className="text-xs text-muted-foreground">{t("settingsBoundary")}</p>
  {locale!=="en"&&locale!=="zh-CN"?<p className="text-xs">{t("fallback")}</p>:null}
  <label className="block text-sm">{h("protocol")}<select name="review_protocol" className="ml-2 max-w-full rounded border bg-background p-2" value={settings.review_protocol} onChange={e=>onChange(switchCoverageProtocol(settings,e.target.value))}>
   <option value="segment_coverage.v1">{h("legacy")}</option><option value="hierarchical_review.v1">{h("hierarchical")}</option>
  </select></label>
  {settings.review_protocol==="hierarchical_review.v1"?<p className="text-xs text-amber-700 dark:text-amber-300">{h("qualification")}</p>:null}
  {settings.review_protocol==="hierarchical_review.v1"?<p className="text-xs text-muted-foreground">{h("resourcePolicy",{rawBytes:coverageRegistry.review_protocols["hierarchical_review.v1"].raw_source_window_bytes,outputTokens:d.partition_output_tokens})}</p>:null}
  <label className="block text-sm">{t("mode")}<select className="ml-2 rounded border bg-background p-2" value={settings.mode} onChange={e=>onChange({...settings,mode:e.target.value})}>
   {coverageRegistry.modes.map(mode=><option key={mode} value={mode} disabled={settings.review_protocol==="hierarchical_review.v1"&&mode==="enforced"}>{t(`mode_${mode}`)}</option>)}</select></label>
  <label className="flex gap-2 text-sm"><input type="checkbox" checked={settings.model_trial} disabled={settings.mode==="source_shadow"} onChange={e=>onChange({...settings,model_trial:e.target.checked})}/>{t("trial")}</label>
  <p className="text-xs">{t("trialCost",{requests:settings.model_trial&&settings.mode!=="source_shadow"?d.pilot_requests:0,tokens:settings.model_trial&&settings.mode!=="source_shadow"?d.pilot_tokens:0})}</p>
  <details><summary className="cursor-pointer text-sm">{t("resources")}</summary><div className="mt-2 grid gap-2 sm:grid-cols-2">
   {coverageRegistry.editable_limits.map(key=>{const min=(coverageRegistry.minimum_limits as Record<string,number>)[key]??1;return <label key={key} className="text-xs">{t(`limit_${key}`)}<input className="mt-1 w-full rounded border bg-background p-2" type="number" min={min} max={(d as Record<string,number>)[key]} value={settings.limits[key]??(d as Record<string,number>)[key]} onChange={e=>{const n=Number(e.target.value);if(Number.isSafeInteger(n)&&n>=min&&n<=(d as Record<string,number>)[key])onChange({...settings,limits:{...settings.limits,[key]:n}});}}/></label>;})}
  </div></details>
  <ActionButton type="button" onAction={onSave} resetKey={settings} pendingLabel={t("saving")} successLabel={t("saved")} errorLabel={t("saveFailed")} className="rounded border px-3 py-2 text-sm">{t("save")}</ActionButton>
 </section>;
}
