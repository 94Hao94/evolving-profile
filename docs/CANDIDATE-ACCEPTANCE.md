# Candidate acceptance / 候选包验收

Preparation snapshot: fresh local candidate checks passed on macOS, 2026-10-18. These checks
are not publication or full native-host certification. Current publication status is tracked separately
in the release ledger and GitHub. This source snapshot is the input to source-only ZIP/tar packaging;
the external PACKAGE.json/SHA256SUMS record the final archive hashes and round-trip verification.

| Fresh check | Actual result |
| --- | --- |
| Clean dependency provisioning | New candidate-directory `npm ci` and frozen `uv sync` passed; no linked development node_modules/venv |
| Actual installer build | SDK then Console built; initial and repeated build-only runs passed, local env preserved |
| Python scoped regression | 2221 passed,137 subtests passed,3 skipped |
| Host preparation subset |89 passed; overlaps scoped Python results |
| Installer/launcher/preflight/scan subset |28 passed before final metadata cases; overlaps scoped results, not additive |
| API MCP routing/coercion |53 passed with isolated fixtures |
| Console / TypeScript |96 files /666 passed; TypeScript passed |
| Configuration round trip | Actual CLI preview/apply/restore on synthetic audit-owned JSON preserved unrelated entry and restored exact bytes |
| Packaged protocol | WorkBuddy/Doubao profiles initialized/listed21 read-only tools; no native task, knowledge or provider calls |
| Fresh Console startup | Actual documented CLI, isolated state, no explicit host-source override; new management API returned8profiles and writes disabled |
| Runtime version projection | Actual isolated runtime changed from5.1/development fallback to5.1.2/candidate only after explicit projection;4new cases RED→GREEN |
| Documentation | Bilingual routes/instructions, local links and copyable shell/JSON syntax checked; one independent first-reader review |

The preview intentionally had no configured data API/database/model. Its management route and
runtime projection were exercised, not full memory operations. `/api/version` depends on a live
data API and was unavailable in this preview; it is not counted as a successful end-to-end check.
Initial installer-failure paths were fixture tests, not deliberate failures on a real database.

## Three skipped checks, not passes

- Two historical EP2.1 rollback tests require separately supplied external rollback script/baseline.
  Those historical assets are not distributed; current synthetic installer recovery tests did run.
- One explicitly enabled operator-local deployment audit is skipped because a new source candidate
  is not permission to upgrade or inspect a private installation as if this candidate were deployed.

## Reader review and known limits

The fresh reader answered all8 installation/use questions: correct supplied-candidate source,
actual routes, genuine binding, ordinary-Chat limits, maturity, summary-vs-source, permissions and
native acceptance. One Important runtime-version projection gap was fixed and actually verified.
A source-authority scope note was clarified so Codex paths cannot be read as universal host authority.
Late fixes were author-verified via targeted regressions and scoped suite, not a claimed second review.

One retained minor: bare Console CLI defaults to all interfaces. The README/setup commands
explicitly use127.0.0.1 and disclose the legacy behavior; it is not an approved public deployment.
Dependency install emitted upstream deprecation notices. No new dependency vulnerability audit
was performed; earlier dependency-risk documentation is historical, not a new clean bill of health.

## Not certified

At the preparation snapshot no GitHub publication, real new-client task, Windows executor,
provider/database quality test or whole-history extraction had been performed. Publication may
advance separately; it does not certify the unexecuted host/model/platform checks.
Windows/PowerShell/WSL/Linux/remote/TLS, physical mobile, all lazy tool branches, automatic capture,
every model/document collection and final-answer benefit remain separate acceptance boundaries.
Source text scanning does not certify binary-image privacy, dependency licensing or supply-chain safety.
No production9999 update, new host registration, full database restore or whole-history quality claim.
