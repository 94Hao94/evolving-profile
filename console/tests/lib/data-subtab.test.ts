import { describe, expect, it } from "vitest";
import { normalizeDataSubTab } from "@/lib/data-subtab";

describe("normalizeDataSubTab", () => {
  it("keeps legacy guidance-v1 bookmarks on the preferences view", () => {
    expect(normalizeDataSubTab("guidance-v1")).toBe("preferences");
  });

  it("falls back unknown data subtabs to world instead of rendering an empty page", () => {
    expect(normalizeDataSubTab("retired-view")).toBe("world");
  });

  it("keeps supported data views unchanged", () => {
    expect(normalizeDataSubTab("experience")).toBe("experience");
    expect(normalizeDataSubTab("preferences")).toBe("preferences");
  });
});
