import { defineRouting } from "next-intl/routing";
import { locales, defaultLocale } from "./config";

export const routing = defineRouting({
  locales,
  defaultLocale,
  // Existing Evolving Profile bookmarks include the locale. Keep it explicit
  // so /zh-CN/banks/... remains a stable, shareable address without a redirect
  // loop or a cookie-dependent route rewrite.
  localePrefix: "always",
});
