# Evolving Profile API

The PostgreSQL-backed EP data plane stores Banks, facts, experiences, entities
and temporal relations, and exposes retention, hybrid retrieval and HTTP MCP.
It is not the complete EP host stack: Controller, Hook, Guidance, Scenario
Summary workers and host delivery receipts are separate integrations.

## Install from this checkout

See [Local setup](../docs/LOCAL-SETUP.md). Use the checked-out source, not an
assumed public PyPI package or an upstream Docker image with a similar name.
The product version is `../VERSION`; internal component versions are separate.

```bash
./scripts/install-ep51.sh --mode local --no-launch
```

Base `uv sync --project api` does not install embedded PostgreSQL or local ML.
Install only the extras needed by the selected route:

```bash
# Optional embedded database, may download platform-specific binaries.
uv sync --project api --extra embedded-db
# Optional local embeddings/reranking; sizeable dependencies and model files.
uv sync --project api --extra local-ml
# Specify both in the same command when both are needed.
uv sync --project api --extra embedded-db --extra local-ml
```

`local-onnx` is a separate optional ONNX runtime. Installing an extra is not
proof that a selected model path exists or loads successfully.

## Configure before launch

Edit the generated local `.env` from the repository root. Never commit it.

| Variable | Meaning |
| --- | --- |
| `EVOLVING_PROFILE_API_DATABASE_URL` | Existing PostgreSQL/pgvector URL, or explicit `pg0` after installing `embedded-db` |
| `EVOLVING_PROFILE_API_LLM_PROVIDER` | Actual configured provider; `openai` supports compatible services |
| `EVOLVING_PROFILE_API_LLM_MODEL` | Model supported by that provider |
| `EVOLVING_PROFILE_API_LLM_API_KEY` | Your local credential |
| `EVOLVING_PROFILE_API_LLM_BASE_URL` | Compatible service URL when not the provider default |
| `EVOLVING_PROFILE_API_EMBEDDINGS_PROVIDER` | Template uses the separate `openai` embedding route |
| `EVOLVING_PROFILE_API_EMBEDDINGS_OPENAI_MODEL` | Actual embedding model; dimension changes require index migration/rebuild |
| `EVOLVING_PROFILE_API_EMBEDDINGS_OPENAI_API_KEY` | Embedding credential; a chat-only subscription may not offer embeddings |
| `EVOLVING_PROFILE_API_EMBEDDINGS_OPENAI_BASE_URL` | Embedding endpoint, independent of chat |
| `EVOLVING_PROFILE_API_RERANKER_PROVIDER` | Template uses `rrf`, rank fusion without learned reranker inference |

## Start and verify

From the repository root, after configuration, in terminal 1:

```bash
uv run --project api evolving-profile-api --host 127.0.0.1 --port 8888 --workers 1
```

In terminal 2, after building:

```bash
node --env-file=.env console/bin/cli.js --hostname 127.0.0.1 --port 9999 --api-url http://127.0.0.1:8888
```

Open `http://127.0.0.1:9999` and create an empty Bank of your own. Check:

```bash
curl --fail http://127.0.0.1:8888/health
curl --fail http://127.0.0.1:8888/v1/default/banks
```

Health and Bank listing prove startup, not semantic quality. Model connection,
retrieval, source readback and host delivery need separate checks. Unconfigured
optional Controller/Guidance services must remain unavailable/unknown, not
erase Bank data or become false zero counts.

The API entrypoint discovers `.env` from its working directory/parents with
override semantics. A conflicting blank `.env` can override exported values.
The Console production CLI does not automatically load the root `.env`, hence
Node's explicit `--env-file`. Bind locally; public exposure needs separate
access control. See Local setup for upgrade/failure/rollback boundaries.

## Distinct MCP interfaces

- API HTTP MCP: `/mcp` when `EVOLVING_PROFILE_API_MCP_ENABLED=true`.
- Data-plane stdio entrypoint: `evolving-profile-local-mcp`.
- EP host/controller entrypoint: `host-adapter/evolving_profile_controller_mcp.py`.

These are not interchangeable. An API HTTP initialize response does not prove
host `user_recall`, `agent_research`, Scenario Summary, Hook capture, context
delivery or final-answer adoption. Installing API/Console does not register EP
in Codex or automatically configure transcript capture.

## Attribution and distribution boundary

See [NOTICE.md](../NOTICE.md) and source licenses for upstream Hindsight
acknowledgment. Upstream package names/images/docs are not a substitute for
this EP checkout. No production Bank, credential, private transcript or local
model weights are included. Read the root README for product logic and
`docs/RELEASE-NOTES-5.1.0.md` for release verification and known limits.
