import { describe, expect, it } from "vitest";
import { resolveConsoleOrigin } from "@/lib/console-origin";

describe("resolveConsoleOrigin", () => {
  it("uses the current preview host and port", () => {
    expect(resolveConsoleOrigin("http://localhost:10002/zh-CN/banks/demo", undefined)).toBe("http://localhost:10002");
  });

  it("uses the configured port when the runtime is behind a proxy", () => {
    expect(resolveConsoleOrigin("http://127.0.0.1:3000/health", "10002")).toBe("http://127.0.0.1:10002");
  });
});
