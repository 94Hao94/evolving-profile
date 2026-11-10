"use client";
import { useLocale, useTranslations } from "next-intl";
import { Button } from "./ui/button";
import { bankRoute } from "@/lib/bank-url";
import { withBasePath } from "@/lib/base-path";
import type { BankSelection } from "@/lib/bank-selection";

export function BankAccessNotice({status,requestedBank,primaryBank,primaryReady,onRetry,returnQuery="?view=data"}:{
  status:BankSelection["status"]|"loading";requestedBank:string|null;
  primaryBank:string|null;primaryReady:boolean;onRetry:()=>void;returnQuery?:string;
}) {
  const t=useTranslations("bankSelection");
  const locale=useLocale();
  const state=status==="ready"?"loading":status;
  return <section role="status" className="mx-auto my-10 w-full max-w-2xl rounded-xl border bg-card p-6 shadow-sm" data-testid="bank-access-notice">
    <h1 className="mb-3 text-xl font-semibold">{t(`title_${state}`)}</h1>
    <p className="text-sm text-muted-foreground">{t(`detail_${state}`)}</p>
    {requestedBank && <p className="mt-4 break-all text-sm">{t("requested")}: <strong>{requestedBank}</strong></p>}
    {primaryBank && <p className="mt-2 break-all text-sm">{t("configuredPrimary")}: <strong>{primaryBank}</strong></p>}
    <div className="mt-6 flex flex-wrap gap-3">
      {primaryReady && primaryBank && state!=="loading" &&
        <Button asChild><a href={withBasePath(`/${locale}${bankRoute(primaryBank,returnQuery)}`)}>{t("goPrimary")}</a></Button>}
      {state!=="loading" && <Button variant="outline" onClick={onRetry}>{t("retry")}</Button>}
    </div>
  </section>;
}
