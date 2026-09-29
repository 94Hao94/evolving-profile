# Repository Guidance

When asked to update, package, contribute, or release Evolving Profile:

1. Read `docs/RELEASING.md`, `docs/RELEASE-LEDGER.md`, `NOTICE.md`, and the current `CHANGELOG-*.md` before acting. Treat `VERSION` as the product version; component package versions may differ.
2. Inspect the current Git branch, remotes, worktree changes, upstream PR state, and the actual development source. This checkout is a sanitized distribution, not the private runtime or a guarantee that the newest development changes have been copied here.
3. Preserve author and upstream acknowledgments accurately. Git commit authors, the EP distribution author, repository owners, and Hindsight acknowledgments are different categories; do not infer identity or contribution from an email alone.
4. Update README, NOTICE, CHANGELOG, VERSION, UI product labels, release notes, and the release ledger consistently. Use `docs/RELEASE-NOTES-TEMPLATE.md`; record actual tests, known limits, migration, rollback, and separate PR/Tag/Release statuses.
5. Run `python3 scripts/release-preflight.py --json` and `./scripts/verify-package.sh`, plus tests/builds and visual or host-chain checks relevant to the changed components. Scan the final package for secrets and personal memory data.
6. Do not push, create a PR, tag, publish a GitHub Release, or overwrite the public branch merely because local preparation is complete. Those external actions require the user's instruction for that release.
