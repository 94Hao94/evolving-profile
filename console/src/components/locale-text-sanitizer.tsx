"use client";

import { useEffect } from "react";
import { inlineUiText, isKnownInlineUiText } from "@/lib/inline-i18n";

const ATTRIBUTES = ["title", "aria-label", "placeholder", "alt"];

function shouldSkip(node: Node): boolean {
  const parent = node.parentElement;
  if (!parent) return true;
  return Boolean(parent.closest("script,style,pre,code,[data-i18n-ignore='true']"));
}

function localize(root: Node, locale: string) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: Text[] = [];
  let node: Node | null;
  while ((node = walker.nextNode())) texts.push(node as Text);
  for (const text of texts) {
    if (shouldSkip(text)) continue;
    const value = text.nodeValue ?? "";
    if (!isKnownInlineUiText(value)) continue;
    const translated = inlineUiText(value, locale);
    if (translated !== value && translated.trim()) text.nodeValue = translated;
  }
  const elements = root instanceof Element ? [root, ...Array.from(root.querySelectorAll("*"))] : Array.from(document.querySelectorAll("*"));
  for (const element of elements) {
    for (const attribute of ATTRIBUTES) {
      const value = element.getAttribute(attribute);
      if (!value) continue;
      if (!isKnownInlineUiText(value)) continue;
      const translated = inlineUiText(value, locale);
      if (translated !== value && translated.trim()) element.setAttribute(attribute, translated);
    }
  }
}

export function LocaleTextSanitizer({ locale }: { locale: string }) {
  useEffect(() => {
    document.body.dataset.i18nSanitizer = locale;
    localize(document.body, locale);
    // Hydration can replace server text after the first effect. Re-scan a few
    // animation frames so legacy literal nodes settle into the active locale.
    const timers = [100, 400, 900, 1600].map((delay) => window.setTimeout(() => localize(document.body, locale), delay));
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "characterData" && record.target.parentElement) localize(record.target.parentElement, locale);
        for (const added of Array.from(record.addedNodes)) if (added.nodeType === Node.ELEMENT_NODE) localize(added, locale);
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
    return () => { observer.disconnect(); timers.forEach((timer) => window.clearTimeout(timer)); };
  }, [locale]);
  return null;
}
