# Evolving Profile 5.1.2 — RC1

Status: **release candidate, not all-platform stable**; tag `v5.1.2-rc.1`.
Actual Release/PR/merge states belong in the release ledger. VERSION is the product authority;
config/release-manifest.json is its checked projection. Internal component versions and old
branch names are not product-version authorities. Read README for the full product, CHANGELOG
for changes, AGENT-SETUP for installation requests and AGENT-USAGE for daily tool selection.

## What is implemented, what is verified

| Level | Meaning in this candidate |
| --- | --- |
| Existing, primarily exercised route | macOS/Codex memory planes, conditional preferences, layered scenario/source navigation and observable flow. Not a whole-history accuracy/benefit benchmark. |
| New management functionality implemented and locally exercised |8profiles, metadata discovery, previews, protocol feedback, details/guidance and bilingual/scroll/responsive Console behavior. |
| EP-side protocol tested in isolation | Read-only stdio catalog/policy, optional authenticated HTTP fixtures, identity separation and cleanup. Not target-client receive/use proof. |
| Prepared, native acceptance pending | Claude surfaces, Hermes, WorkBuddy, Doubao native lifecycle/source/binding and Windows/PowerShell execution. |
| Operator-dependent optional capabilities | RAG, embedding/rerank, JEV, capture, backups and models require actual configuration, resources and their own acceptance. |

## Source and verification provenance

The candidate combines the prior sanitized5.1.1 distribution with reviewed cross-host preparation
changes. The author's private memory, keys, transcripts, live receipts, model weights and absolute
runtime paths are not distribution inputs. Existing illustrative images retain their original captions;
they are not screenshots or benchmarks of every new host.

Prior implementation evidence: scoped Python2172+107subtests, Console666, API MCP62, isolated
protocol/policy checks and actual local macOS Console deployment. Those numbers describe earlier
work, not automatically this candidate's fresh results. Fresh package checks are recorded in
[candidate acceptance](CANDIDATE-ACCEPTANCE.md), including failures/skips and unexecuted items.

## Installation and operation boundaries

- Exact RC tag or named verified archive first; do not substitute the old public branch.
- Build-only installer is not a full one-click service installer. Backend, database, embeddings,
  host registration and permitted workers have separate readiness requirements.
- New-host capture stays off; web Apply/Restore remain disabled in preparation mode. Explicit
  reviewed CLI operations remain available with revision checks and confirmation.
- Missing Hooks: project rules/Skill guidance may help selection, never guarantee every-turn use.
- Navigation-generated check IDs are not trusted Hook binding. See AGENT-USAGE.
- A single optional HTTP gateway serves one EP data owner; no multi-tenant Bank isolation claim.
- Real Windows, physical mobile, remote/TLS, every lazy tool branch, all models and full history
  have not been certified. A local healthy endpoint or tools/list does not fill these cells.
- No automatic memory import, history re-extraction, optional feature enabling or GitHub publication.
- The verified runtime-metadata projection is explicit, revision-checked and backed up; build-only
  setup does not overwrite a running installation's version. Bare CLI all-interface default remains
  a documented legacy limit; all provided launch commands explicitly select loopback.

## 中文摘要

本版是**5.1.2 RC1候选**，不是全平台稳定认证版。主要新增宿主准备管理、跨平台基础
和给不同Agent看的使用协议。已有的五维偏好、用户/智能体记忆、三层情景及来源逻辑
继续完整介绍；不把README改成更新流水账。哪些实现、哪些协议通过、哪些真实宿主待测
分别列明。新包的实际验收看CANDIDATE-ACCEPTANCE，不把之前测试数字重复算成本次通过。

保留Hindsight来源声明、原许可和CCY发行署名。个人预发布不表示上游接受、主分支合并或
上游GitHub Release已发生，也不替换本机当前运行服务。
