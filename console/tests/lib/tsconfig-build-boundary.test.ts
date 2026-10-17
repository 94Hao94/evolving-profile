import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

it("does not typecheck copied standalone output as a second source tree", () => {
  const config = JSON.parse(readFileSync(new URL("../../tsconfig.json", import.meta.url), "utf8"));
  expect(config.exclude).toContain("standalone");
  expect(config.exclude).toContain(".next/standalone");
});

it("uses the build-ID-verified standalone packager instead of the first server.js found", () => {
  const pkg = JSON.parse(readFileSync(new URL("../../package.json", import.meta.url), "utf8"));
  expect(pkg.scripts["build:standalone"]).toBe("node scripts/package-standalone.mjs");
});
