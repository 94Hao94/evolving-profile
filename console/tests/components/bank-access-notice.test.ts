import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { NextIntlClientProvider } from "next-intl";
import { describe,it,expect } from "vitest";
import en from "../../src/messages/en.json";
import zh from "../../src/messages/zh-CN.json";
import { BankAccessNotice } from "@/components/bank-access-notice";

describe("bank access boundary",()=>{
  it.each(["en","zh-CN"])("shows missing bank and explicit primary recovery in %s",locale=>{
    const html=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale,
      messages:locale==="en"?en:zh,children:createElement(BankAccessNotice,{
        status:"missing",requestedBank:"stale",primaryBank:"actual/main",primaryReady:true,
        returnQuery:"?view=profile",onRetry:()=>{},
      })}));
    expect(html).toContain(locale==="en"?"Memory bank not found":"记忆库不存在");
    expect(html).toContain(`/${locale}/banks/actual%2Fmain?view=profile`);
    expect(html).not.toContain(locale==="en"?"No operations":"暂无操作");
  });
  it("does not offer primary redirect when existence is unknown",()=>{
    const html=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale:"en",messages:en,
      children:createElement(BankAccessNotice,{status:"unavailable",requestedBank:"other",
        primaryBank:"main",primaryReady:false,onRetry:()=>{}})}));
    expect(html).toContain("Unable to verify"); expect(html).not.toContain("href=");
  });
});
