# Deployment: from source to a connected host

[简体中文](DEPLOYMENT-中文.md) · [Host-specific setup](HOST-SETUP.md) · [Agent requests](AGENT-SETUP.md)

This guide targets a new **local macOS installation**. Linux needs platform
prerequisites checked; native Windows and cloud-host access are not certified.
The product version is [VERSION](../VERSION). The existing contribution branch
is still named `release/5.1.0`; its name is not the installed patch version.
No private Bank, provider account, transcript or model weights are bundled.

For this candidate use the exact `v5.1.2-rc.1` tag or named verified archive; see
[candidate setup](CANDIDATE-SETUP.md). Older branch/tag assets are not this candidate.
After setup, the Agent also needs [daily operating guidance](AGENT-USAGE.md).
After verifying the actual running candidate directory, complete the explicit
[runtime version projection](CANDIDATE-SETUP.md#project-verified-version-metadata-into-the-selected-runtime);
build-only setup does not overwrite an existing installation's release metadata.

## Choose the level you need

| Level | What is running | What it does not establish |
| --- | --- | --- |
| A: API + Console | Database-backed memory API and browser UI | Host tools, automatic capture or preferences |
| B: explicit MCP tools | A + Controller + host MCP registration | Prompt hooks or background extraction |
| C: automatic lifecycle | B + reviewed hooks + configured workers | Every turn benefiting, all historical sources covered |

Start with A, then B. Enable C only after a fresh natural task proves the host's
event format, source identity, write policy and receipts. Claude Code CLI, the
desktop **Code** tab and ordinary Claude Desktop **Chat** are different surfaces.
One-command **build** is available; one-command complete host onboarding is not.

## 1. Requirements and download

Install Git, Python3.11+, `uv`, Node20.9+ and npm through their official channels.
Prepare PostgreSQL with pgvector and your own chat/embedding services. A coding
subscription's chat key may not support embeddings. CPU/local models require
their own dependencies, memory and load tests; they are not downloaded here.

```bash
cd /path/to/extracted-evolving-profile
./scripts/install-ep51.sh --mode local --no-launch
```

The script installs base dependencies, builds the SDK before Console, and
creates `.env` only if absent. It does not install system prerequisites, create a
database, start services, register hosts or enable RAG/JEV/cloud. `--dry-run`
previews without writes; `--skip-deps` is not for a fresh install. The script name
tracks the5.1 line; read VERSION for the patch. See [upgrade/rollback](LOCAL-SETUP.md).

## 2. Set credentials locally and choose one Bank

Edit the generated `.env` in a local editor, never in public chat or Git:

| Setting | Meaning |
| --- | --- |
| `EVOLVING_PROFILE_API_DATABASE_URL` | Your PostgreSQL/pgvector URL |
| `EVOLVING_PROFILE_API_LLM_PROVIDER`, `_MODEL`, `_BASE_URL`, `_API_KEY` | Backend extraction/chat provider; not the host's own account |
| `EVOLVING_PROFILE_API_EMBEDDINGS_PROVIDER` and matching provider fields | A separately verified embedding route |
| `EVOLVING_PROFILE_API_RERANKER_PROVIDER=rrf` | Rank fusion without downloading a learned reranker; not a cross-encoder |
| `EP_BANK_ID=personal-memory` | Installation convention, not a universal environment override |

Use [API configuration](../api/README.md) for provider-specific fields and database
extras. The embedded route requires `uv sync --project api --extra embedded-db`
and an explicitly configured database URL, not just a blank PostgreSQL setting.
Do not install every ML extra by default.

**For the copyable route use `personal-memory`.** Create/select that Bank in the
Console after API startup. This release's stdio adapter still has a fixed Bank
constant; changing `EP_BANK_ID` or the UI selector alone does not rebind it.
Custom-Bank deployments must align adapter, access policy, Guidance config,
workers and Console and verify actual receipt Bank IDs. Do not claim an arbitrary
Bank is selected because an environment label changed.

Keep secrets out of registration commands. A masked key in the UI is not proof
the API loaded it. Existing installations must preserve their own state/config;
the examples below are for a new installation only.

## 3. Prepare Controller and Guidance configuration

The minimal public Controller inputs are
[`install-controller-contract.example.json`](../config/install-controller-contract.example.json)
and [`install-access-policy.example.json`](../config/install-access-policy.example.json).
They enable ordinary governed routing without the optional experimental memory-OS
or an author's old fast-recall snapshot. They contain no personal data.

For first use, create the empty Guidance registry configuration with an absolute
path. Run from the checkout; this refuses to replace an existing configuration:

```bash
python3 - <<'PY'
import json
from pathlib import Path
root = Path.home() / '.evolving-profile/guidance-v1'
root.mkdir(parents=True, exist_ok=True)
config = root / 'guidance-v1.json'
with config.open('x', encoding='utf-8') as stream:
    json.dump({'registry': str(root / 'guidance.sqlite3'),
               'bank_id': 'personal-memory'}, stream, indent=2)
PY
```

If it reports `FileExistsError`, inspect/reuse the existing configuration; do
not delete it or overwrite its Bank. An empty registry is normal: the user's
preferences have not been extracted yet. Copying the author's preferences is not
an installation step. Replace `.env`'s relative Guidance paths with your absolute
checkout `/guidance` and the configuration above if those fields are used by
workers. MCP commands below pass absolute overrides independently.

## 4. Start backend and web UI

Use three separate terminals, each at the checkout root. The terminals own these
foreground processes; closing them stops their services. Do not run a second
copy if a port is already occupied. Inspect the listener, choose free ports and
change every related URL rather than terminating unrelated processes.

**Terminal1 — API:**

```bash
uv run --project api --env-file .env evolving-profile-api --host 127.0.0.1 --port 8888 --workers 1
```

**Terminal2 — QueryController:**

```bash
HAM_OS_STATE_ROOT="$HOME/.evolving-profile/memory-os" \
uv run --project api --env-file .env python controller/controller.py \
  --host 127.0.0.1 --port 12079 --upstream http://127.0.0.1:8888 \
  --contract config/install-controller-contract.example.json \
  --policy config/install-access-policy.example.json
```

The Controller forwards the existing API and adds governed query routes. It is
not a second memory database. Your private, reviewed Controller configuration
can replace the two example paths after testing; never overwrite an existing
contract with the minimal example to silence a failure.

**Terminal3 — production Console:**

```bash
EVOLVING_PROFILE_RECOVERY_SCRIPT="$(pwd -P)/host-adapter/memory_recovery.py" \
EVOLVING_PROFILE_PYTHON="$(pwd -P)/api/.venv/bin/python" \
node --env-file=.env console/bin/cli.js --hostname 127.0.0.1 --port 9999 --api-url http://127.0.0.1:8888
```

Open [English UI](http://127.0.0.1:9999/en) or
[简体中文 UI](http://127.0.0.1:9999/zh-CN). On macOS, `open
http://127.0.0.1:9999/en` opens the browser; on Linux use the desktop's browser
opener. Browser access, API health and model validity are separate checks:

```bash
curl --fail http://127.0.0.1:8888/health
curl --fail http://127.0.0.1:12079/v1/status
```

Only after both respond, continue to [host registration](HOST-SETUP.md).
An API `/mcp` endpoint is not the same as the EP Controller's stdio tools.
Bind to loopback. Do not publish ports or disable host permissions to make setup work.

The two Console environment prefixes bind the web recovery runner to this
checkout's actual interpreter/script. Without them a fresh production standalone
may not resolve those paths. They do not authorize jobs or make every legacy
managed-service control portable to a manual installation.

## 5. Configuration recommendations in the web UI

Select your Bank → **Memory bank configuration**. Labels follow the UI language;
recommended choices are not a claim that every control applies to every startup mode.

| Area | Start here | Verify before relying on it |
| --- | --- | --- |
| Providers | One working primary, then an independently tested fallback | Backend's effective model/base URL and masked credential state after save/reload |
| User / agent memory | Retain intended modules; turn off only what you do not use | `record`, `retrieve` and `inject` are distinct; switch-on does not start a missing worker |
| Retrieval relevance | Start with the configured weak-related/background-friendly policy | Entirely unrelated content stays excluded; weak candidates are not facts |
| Embedding / rerank models | Verify online embedding first, or test a local model's actual load | Same model/dimensions as the active index; change requires rebuild, not silent reuse |
| Scenario summaries | Keep layered navigation; bounded source readback when insufficient | Published source revision, scope and coverage; no all-history processing by default |
| External RAG | Off until a specific folder/collection is needed | Index state, model binding and source isolation; read-only source selection is not EP fact import |
| JEV | Off initially; optional assist after a successful connection test | Selected stages actually produce judgments; rule fallback on errors; risk gate stays separately opt-in |
| Backups | Local first, choose retention and inspect restore evidence | A scheduled task is not a verified backup; cloud remains opt-in |

**Configuration ownership matters.** The manual API command reads the checkout
`.env`. Console's managed Provider profile normally targets
`~/.evolving-profile/profiles/evolving-profile-api.env`; they are not automatically
the same file. Saving in the web UI must not be called “applied” until the process
uses that intended effective profile and has been reloaded through its supported
apply flow. For a manual install, explicitly update the owned local `.env` and
restart only its API after a backup, or configure and verify the supported managed
profile path. Never copy displayed mask characters into a real key.

State files and managed service controls are operator-local. An alternate
`EVOLVING_PROFILE_STATE_ROOT` is a separate installation, not permission to
control the default installation's daemons. Several host readers remain home-
scoped, so changing that variable alone does not create full multi-instance isolation.

**Flow layout:** use the chain page's gear → Save layout. Geometry is shared in
this installation's `config/topology-layout.json` under its state root; the badge
shows the shared revision. Browser origins/ports do not own separate saved
geometry anymore. Existing v7 browser settings are preserved as an explicit
unsaved recovery draft; loading a draft does not publish it. A conflicting tab
cannot overwrite newer settings. Text overrides are separated by language.
If a save lock survives a process crash, the UI reports busy rather than breaks
another writer's lock: verify the owning process has exited before operator
recovery, and preserve the current file and `.previous`. Do not delete state to
make the diagram look green. A different state root is a different installation,
not a shared layout server across unrelated machines.

## 6. Automatic capture, extraction and optional workers

MCP explicit reads work separately from automation. [Host setup](HOST-SETUP.md)
describes reviewed Codex hooks and the limits of Claude lifecycle reuse.
After capture is verified, the retention dispatcher consumes its queue:

```bash
uv run --project api --env-file .env python host-adapter/retention_worker.py --once
```

This entry runs **one dispatch cycle**, even without `--once`; it is not a
permanent daemon. Configure a scheduler only for this installation, preserve
failures/quarantine and inspect completed operation receipts. It reads the
operator's `~/.evolving-profile/codex.json`; do not assume a Bank UI switch or
`EP_BANK_ID` supplies its API connection and queue configuration.

Codex raw-session discovery can be inspected without model extraction:

```bash
uv run --project api --env-file .env python host-adapter/context-incremental-worker.py --status
```

For a deliberately selected recent Codex session, first run `--discover-only`
with `--session-root`, `--session-id` and `--bank-id`; review its source scope.
Only then opt into `--process --max-jobs 1 --provider-env /absolute/local/provider.env`
with the same scope. `--process` can use provider tokens. Do not point the Codex
scanner at a Claude transcript tree and assume its source format is supported.

Other workers have separate ownership and are not started by the installer.
Run the following only from the checkout and only for the capabilities you chose:

| Entry | Inputs / behavior |
| --- | --- |
| Guidance | Home `guidance-v1/guidance-v1.json`, source API, selected Bank and `EVOLVING_PROFILE_PROFILE_ENV` file; one cycle can process **all changed observations**, not a scoped `--limit` batch |
| Topic catalog | Database URL from `.env`, explicit Bank and output SQLite path; `--limit 500` bounds fetched inventory, not all-history semantic completion |
| Status server | Checkout runtime root, API8888, Controller12079; serves12098, not9998 |
| Recovery | Existing selected persisted job; no global retry/reset implied |

**Guidance (only an empty/new Bank or explicitly authorized changed-observation processing):**

```bash
EVOLVING_PROFILE_PROFILE_ENV="$(pwd -P)/.env" \
EVOLVING_PROFILE_SOURCE_API_URL=http://127.0.0.1:8888 \
EVOLVING_PROFILE_BANK_ID=personal-memory \
uv run --project api --env-file .env python guidance/guidance_worker.py
```

That script reads the profile file itself; loading shell variables alone is not
enough. Its legacy profile parser expects plain `KEY=value` fields; do not use
shell expressions or `export` lines. It may call the configured model and rebuild
derived mental models. Do not run it across a large existing Bank as a startup probe.

**Topic directory, after database access is configured:**

```bash
uv run --project api --env-file .env python guidance/topic_catalog_worker.py \
  --bank-id personal-memory --limit 500 --output "$HOME/.evolving-profile/catalog/topics.sqlite3"
```

**Status server, in another owned terminal:**

```bash
EVOLVING_PROFILE_RUNTIME_ROOT="$(pwd -P)" \
EVOLVING_PROFILE_API_URL=http://127.0.0.1:8888 \
EVOLVING_PROFILE_CONTROLLER_URL=http://127.0.0.1:12079 \
EVOLVING_PROFILE_STATUS_PORT=12098 \
uv run --project api --env-file .env python status/evolving_profile_status_server.py
```

Before starting Console, set `EVOLVING_PROFILE_STATUS_API_URL=http://127.0.0.1:12098`
in its owned `.env`; some legacy routes otherwise default to9998. Restart only
that Console to reload environment. Use `/v1/status` on the Controller, not an
invented status-server `/health` path. Missing panel evidence remains unknown.

For recovery prefer the web **Supplement and extract** flow: inspect a bounded
plan and its actual job ID. An existing approved job can be resumed with
`uv run --project api --env-file .env python host-adapter/memory_recovery.py --run-job REAL_JOB_UUID`.
Replace that token with the persisted UUID; do not run it as a startup check or
requeue completed work under a new ID. Model/side effects depend on that job.

Validate each owned cycle before scheduling. Missing optional-service panels
must remain unavailable/unknown, not be reported as healthy.
The macOS plist files are templates: render all `__EP_HOME__` paths and remove
the sample historical start date in favor of your explicitly chosen new-install
date. Do not bootstrap the templates unchanged or re-extract all old history.

## 7. Acceptance and troubleshooting

For each host record **passed / failed / unavailable / not tested** separately:

1. API health, database and a real configured model route.
2. Console in the chosen language; a new Bank may legitimately be empty.
3. Controller status with the intended upstream.
4. Host-native MCP listing and a real task's tool call, not just config presence.
5. Candidate/returned body, original-source readback and delivery as separate facts.
6. A permitted natural task's capture → queue → completed extraction → visible
   memory, if automatic recording was enabled. Never seed production with tests.
7. Chain page binding to that task; unknown answer adoption stays unknown.

If no tool appears, check absolute executable paths, environment and duplicate
server names before restarting the host. If tools appear but return empty,
check Bank, source coverage, module switches and relevance rather than treating
it as a transport failure. If a UI save does not affect the API, check the profile
ownership described above. Empty process categories need real qualifying source
evidence; they are not filled with synthetic successes.

Read [dependency risks](DEPENDENCY-RISKS.md) and [release ledger](RELEASE-LEDGER.md).
No procedure here moves old tags or certifies every host/platform/history.

## 8. Stop, restart and back up this installation

For the foreground commands above, use **Ctrl-C in that process's terminal**.
Stop owned capture/schedules first; wait for in-flight writes to finish or retain
their operation IDs. Stop owned Console/Status/Controller, then API if required.
Do not kill every Python/Node process or cancel unrelated operations. Restart
API → Controller → Status (if used) → Console, with the same effective profiles,
and repeat health/UI/host checks. MCP stdio is owned by its host, not a separate
server to leave running; refresh its registration/catalog when executable paths change.

For a manual local backup, select a private durable parent and make a new unique
directory. This example backs up configuration/derived queues locally, not the database:

**Before archiving state, quiesce every writer for this installation:** hooks,
MCP processes, retention/Guidance/scenario/recovery workers and web settings writes,
not just the API. Wait for or preserve outstanding jobs. If writers cannot be
stopped, use the database's consistent online snapshot/backup procedure instead
of a live tar of SQLite files. The commands below assume this precondition.

```bash
EP_BACKUP_PARENT="$HOME/EP-backups"
mkdir -p "$EP_BACKUP_PARENT"
EP_BACKUP_DIR="$(mktemp -d "$EP_BACKUP_PARENT/ep-XXXXXX")"
chmod 700 "$EP_BACKUP_DIR"
test ! -f .env || cp -p .env "$EP_BACKUP_DIR/checkout.env"
test ! -d "$HOME/.evolving-profile" || tar --exclude='.evolving-profile/backups' \
  --exclude='.evolving-profile/runtime' -czf "$EP_BACKUP_DIR/operator-state.tgz" \
  -C "$HOME" .evolving-profile
git rev-parse HEAD > "$EP_BACKUP_DIR/source-commit.txt"
cp VERSION package-lock.json "$EP_BACKUP_DIR/"
chmod -R go-rwx "$EP_BACKUP_DIR"
```

State archives can be large; check space first. Include separately the exact host
MCP/Hook/settings files you changed (Codex `config.toml`/`hooks.json`, Claude user/
project settings and/or Desktop JSON), plus the owned service definitions and
effective Provider profile if stored elsewhere. Preserve old matching builds or
their installer backup paths for code rollback. **These files contain secrets
and private memory; do not upload them to GitHub, issue comments or public agents.**

Back up PostgreSQL separately with your DBA/client or a matching `pg_dump`.
For example, after configuring the local libpq service `ep-local` for the intended
database and secure password storage, run
`pg_dump --format=custom --file="$EP_BACKUP_DIR/database.dump" --dbname=service=ep-local`.
This is a template service name, not automatically created by EP; never paste
password-bearing URLs into public commands. Check exit0 and `pg_restore --list`
for the dump, then test restoration only in a **separate disposable database**.
Listing a dump is not a verified restore. A file tar is not a live PostgreSQL backup.

For embedded `pg0`, discover that instance's actual data directory, port and
matching PostgreSQL tools from its configuration/logs; the external `ep-local`
service example does not configure it. Take a logical dump from the correct
running instance or an engine-supported stopped-data backup. Do not copy a live
embedded data directory or assume the `.evolving-profile` tar includes its data.
If neither backup path is available, report backup/upgrade readiness as incomplete.

Restore only the intended installation after preserving new writes; never put an
old queue over already completed operations. Compare source/build/config and
database versions before restoring. UI backup retention does not replace this
first verified recovery drill. Inspect the cloud toggle on a new install: some
legacy no-file defaults show a WPS mirror enabled, which does not install an
uploader. Leave cloud disabled when not chosen; do not start cloud jobs from
that prefilled state. An installed5.1.0 runtime may legitimately differ
from a staged5.1.1 checkout: the live source-of-truth integration audit is opt-in
(`EP_TEST_LIVE_STATE_AUDIT=1`), not permission to mutate live state to pass tests.
