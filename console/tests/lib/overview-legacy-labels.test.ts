import { expect, it } from "vitest";
import { inlineUiText } from "@/lib/inline-i18n";

it.each([
  ["待语义审核", "Pending semantic review"],
  ["已审核偏好", "Reviewed preference"],
  ["未提供", "Not provided"],
  ["级别", "Severity"],
  ["暂无候选回执，不能推断为零候选。", "No candidate receipts are available; this does not imply zero candidates."],
])("translates overview interface label %s without changing source-language copy", (source, english) => {
  expect(inlineUiText(source, "en")).toBe(english);
  expect(inlineUiText(source, "zh-CN")).toBe(source);
});
