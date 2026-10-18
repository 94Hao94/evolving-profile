# 5.1.2 RC1 publication-tree validation — 2026-10-18

This is a new run on the sanitized Git publication tree, not reused private-development results.
Product authority is VERSION5.1.2; channel is candidate; intended tag isv5.1.2-rc.1.

| Scope | Result |
| --- | --- |
| Guidance, Host Adapter, Status, Controller and release scripts |2221 passed,137 subtests,3 skipped |
| Console full suite |96files/666 passed |
| SDK then Console production/standalone |Passed |
| Release metadata/structure/source text scan |Passed |

The skipped cases remain two historical EP2.1 rollback tests requiring separate external assets
and one explicit opt-in private-runtime deployment audit. They are not counted as passing.
No production metadata, Bank, transcript, key, queue or topology layout was imported or changed.

Candidate clean-install, repeat-build, synthetic config round trip, live isolated management API,
runtime-version projection and first-reader evidence remains separately documented in
CANDIDATE-ACCEPTANCE.md. The publication step does not turn those into real target-host evidence.
Native Windows/PowerShell and new-client lifecycle/receive/adoption remain pending.

Release tag/asset and PR readback are performed after publication; use the actual release page,
PR and release ledger, not this pre-publication test snapshot, for completed external state.
Source text checks are not a binary-image, dependency-license or vulnerability certification.
