# EP 5.1 local repair candidate closeout — 2026-10-17

This is a bounded repair-candidate record, not a new GitHub Release or a claim
that all historical semantic summaries and final-answer benefits are certified.
`VERSION` remains 5.1.0. README describes the product; changes belong here and
in the changelog. Existing tags are not moved by local validation.

This is the earlier bounded closeout snapshot. Its eight-advisory observation
below is historical, not the current dependency result. The subsequent
publication pass is recorded in [DEPENDENCY-RISKS.md](DEPENDENCY-RISKS.md):
production-classified audit0; full workspace36, with0critical and residual risks
explicitly retained. Public branch/PR status belongs in the release ledger.

## Repairs and safeguards

- Clean setup builds the workspace SDK before Console, including repeat runs
  with installed dependencies. Dry-run has no filesystem mutation.
- An ordinary failed compiler/build restores the previously completed SDK and
  Console builds. A partially failed backup move preserves both sides, reports
  incomplete rollback and never installs a partial backup over the old tree.
- Release text scanning excludes installed vendors/builds/local untracked
  environment files, but rejects tracked runtime artifacts, tracked local
  environment files and unverified source symlinks. It never follows a source
  link into private directories. This is not a full credential-pattern,
  binary-asset or dependency vulnerability certification.
- Unavailable optional Guidance services no longer erase actual Bank stats or
  fabricate zero candidate/model counts. Numeric service diagnostics no longer
  crash the runtime overview. Prototype-like state names remain numeric counts.
- Fresh-install instructions distinguish build, configuration, API/Console
  startup, host integration, actual model inference and answer adoption.

## Backlog closure boundary

Five eligible original conversation sources were recovered through the existing
operator-only source-bound recovery path after an independent native review.
Review covered 252 messages, 65 episodes and 136 user-message intent witnesses.
Original rejections and attempts were retained; no reset or daily Provider
change was used. This is conversational source coverage, not verification of
historical external artifacts, research, tests or actual audience outcomes.

Native review has explicit non-HTTP provenance; the exact native model identity
remains unknown. No configured EP Provider HTTP requests were used for that
recovery, but native model inference was used. One protected source remains
protected. One environment-only source has no eligible conversation to summarize
and remains waiting rather than receiving invented content.

## Verified finite scope

- Host/Guidance/Status/Controller/scripts: **2,126 passed + 107 subtests**.
- Scoped API source quote, operation lineage, chunking configuration and strict
  structured-output tests: **52 passed**; not the entire API integration suite.
- Console: **90 files / 629 tests**, plus TypeScript checking.
- Actual clean dependency install, SDK/Console production and standalone build.
- Actual isolated API/PostgreSQL/Console startup and API HTTP MCP initialize.
- Real occupied-port and missing-configuration failures, without stopping the
  existing listener or touching production configuration.
- Real injected TypeScript compiler failure restored **6,075 previous artifact
  files byte-identically**, preserving existing `.env` and launch manifest.
- Actual page interactions, service-detail modal and Chinese/English navigation.
- One independent read-only code reviewer reproduced the initial defects and
  revalidated all three Important findings plus one Minor after the author fix.

The isolated Provider was a local synthetic fixture for startup only, not a
real recall/summary semantic benchmark. No production Bank or key was copied.

## Known limits, not silently certified

Experimental whole-history model trials stay off. All-source semantic quality,
blind/ultra-long generalization and native answer adoption remain unmeasured.
This release record does not certify pre-existing cross-Bank refresh race/global
Guidance projection behavior or every runtime unknown-count path. English views
can still contain backend-generated Chinese diagnostics; this is not complete
multilingual content certification. macOS was exercised; Linux target binaries,
Windows-native installation and every host onboarding path were not exercised.

Core defaults remain a repair RC candidate, not an unconditional claim of a
perfect final stable release. Publication requires separate authorization and
must preserve these limits and original test failures.

Fresh `npm audit --omit=dev` still reports **8 advisories: 6 high, 2 moderate,
0 critical**. No automatic force upgrade/downgrade was applied. A text-source
scan passing is not dependency-risk acceptance; these advisories remain a
separate stable-publication risk decision, not silently marked fixed.

中文摘要：本轮闭环的是可恢复积压、全新隔离安装/启动、真实失败回退和本地发行
候选验收。没有把受保护、无正文、未知、未测和实验功能伪装成通过；没有推送 GitHub、
移动旧 Tag、重置尝试次数或更改生产模型配置。安装和运行细节见 `LOCAL-SETUP.md`。
