import { describe, expect, it } from "vitest";
import { bankIdFromPathname } from "@/lib/bank-path";

describe("bankIdFromPathname", () => {
  it("extracts the bank from a locale-prefixed bookmarked route", () => {
    expect(
      bankIdFromPathname(
        "/zh-CN/banks/personal-memory"
      )
    ).toBe("personal-memory");
  });

  it("keeps supporting a route without a locale prefix", () => {
    expect(bankIdFromPathname("/banks/openclaw-trainer")).toBe("openclaw-trainer");
  });

  it("returns null for routes that do not select a bank", () => {
    expect(bankIdFromPathname("/zh-CN/dashboard")).toBeNull();
  });
});
