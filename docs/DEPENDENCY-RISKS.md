# Dependency risk disposition

Checked: 2026-10-17. Scope: this source workspace and the Console standalone
artifact built from its lockfile. Counts are npm package rows, not independent
vulnerabilities. This record is separate from the historical closeout snapshot.

## Current outcome

| Scope | Before | After bounded repairs |
| --- | --- | --- |
| `npm audit --omit=dev` | 8 rows: 6 high, 2 moderate, 0 critical | **0 reported advisories** |
| Full `npm audit` | 43 rows: 1 critical, 33 high, 8 moderate, 1 low | **36 rows: 0 critical, 29 high, 6 moderate, 1 low** |

The remaining 36 rows correspond to four unique advisories; parent tool packages
inherit severity through dependency chains. Neither “zero production-classified
advisories” nor a standalone inventory is a guarantee of zero security risk.
Development/build tools can still process hostile repositories or configuration.

## Repairs applied

- Updated `source-map-js` to **1.2.2**, addressing the indexed source-map offset
  issue [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).
- Updated `handlebars` to **4.7.10**, addressing
  [inline embedding](https://github.com/advisories/GHSA-xw65-4hp5-5hc7),
  [AST confusion](https://github.com/advisories/GHSA-8r5x-fm3f-whwj) and
  [own-property bypass](https://github.com/advisories/GHSA-p8wg-vrv2-v86f).
- Removed the Console's unused `eslint-config-next` dependency. Current ESLint
  configuration does not load it; Next itself was not downgraded. This removes
  that production-classified braces chain, not Jest's remaining development chain.
- Scoped Typography's `postcss-selector-parser` to **7.1.6**, addressing
  [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf).
  This is an explicit cross-major override from upstream's pinned 6.x, not an
  upstream Typography fix. Real AST operations and an explicit Typography CSS
  compile were checked in addition to the ordinary production build.

Fresh `npm ci`, installed resolution checks, SDK build, Console tests,
TypeScript and production/standalone build passed. No `audit fix --force`, parent
package downgrade or advisory suppression was used. Revalidate the override on
future dependency upgrades rather than assuming permanent compatibility.

## Residual risks retained for the RC branch

| Advisory | Evidence and input boundary | Current disposition |
| --- | --- | --- |
| [braces / GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) | SDK Jest/micromatch tooling path; hostile glob patterns can exhaust the tooling process. No patched registry release was available at check time. | Retained development risk; do not run untrusted repository/test patterns. No current Console request path was established. A Jest-chain migration is not silently included. |
| [sprintf-js / GHSA-hp3w-g68c-fv3c](https://github.com/advisories/GHSA-hp3w-g68c-fv3c) | Legacy Jest/Istanbul/argparse path; requires an attacker-controlled format string. Latest available version was still affected. | Retained tooling risk; not presented as fixed by changing dependency classification. |
| [esbuild / GHSA-g7r4-m6w7-qqqr](https://github.com/advisories/GHSA-g7r4-m6w7-qqqr) | SDK bundler resolves an affected version; advisory targets the Windows development server. This workflow bundles on macOS, not esbuild serve. | No Windows-native certification; do not expose the affected dev server. Fix crosses the current bundler's dependency range and needs a separate compatibility change. |
| [OpenAPI generator / GHSA-hhx9-57xq-r5rw](https://github.com/advisories/GHSA-hhx9-57xq-r5rw) | The committed `generated/core/params.gen.ts` also contains the vulnerable helper. Its prototype substitution was reproduced with a harmless marker. Current SDK entry does not export/call the helper, and the built helper body is removed. | **Copied source is not fixed.** Do not import that internal helper or assume regeneration with the old generator is safe. The patched generator requires Node 22.13+, so no undeclared generator/Node migration was performed. Future activation needs source repair/regeneration and API tests. |

The generated-source issue is not dismissed merely because its generator is a
development dependency. Absence of an established current built-call path is
limited evidence, not a proof that all future uses are safe.

## Release meaning

This supports a transparently documented **repair RC branch update**, not an
unconditional stable release or an all-dependency-zero badge. Historical private
memory backlog, source-coverage experiments and final-answer benefit are separate
questions and were not made green by these dependency repairs.

Run both audit commands again before the next release. Advisory metadata and
package availability change over time; keep the exact lockfile, package tree,
build and test evidence together.
