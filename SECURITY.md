# Security and privacy

This distribution is intentionally empty of personal memories. Create a new
Bank before ingesting data. Do not copy a production database, session logs,
MCP receipts, browser profiles, or host configuration into this directory.

API keys are supplied through environment variables or a local, ignored `.env`
file. They are never part of a Bank record and must not be printed in logs.

Before sharing a customized build, run `scripts/check-no-secrets.sh` and inspect
the generated manifest. A clean scan is necessary but not sufficient: review
custom prompts, fixtures, screenshots, and exported databases manually.

Use separate Banks when an Agent must have a narrower permission scope. The
default `personal-memory` Bank is a local development placeholder, not a
permission boundary by itself.
