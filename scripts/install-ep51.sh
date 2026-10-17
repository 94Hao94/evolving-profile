#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="local"
DRY_RUN=0
SKIP_DEPS=0
NO_LAUNCH=0
BUILD_QUARANTINE=""
BUILD_STARTED=0
BUILD_ATTEMPTED=0
BUILD_VERIFIED=0
COMPLETED_BACKUPS=" "
BACKUP_MOVE_IN_PROGRESS=""

build_path() {
  if [[ "$1" == 'client-dist' ]]; then
    printf '%s/evolving-client/dist' "$ROOT"
  else
    printf '%s/console/%s' "$ROOT" "$1"
  fi
}

restore_build_on_failure() {
  install_status=$?
  trap - EXIT
  if (( install_status != 0 && BUILD_STARTED && ! BUILD_VERIFIED )); then
    restore_ok=1
    # A failed cross-filesystem mv may leave only part of its destination.
    # Preserve both sides; destination existence is not proof of a backup.
    [[ -z "$BACKUP_MOVE_IN_PROGRESS" ]] || restore_ok=0
    for build_name in client-dist standalone .next; do
      build_target="$(build_path "$build_name")"
      if [[ "$COMPLETED_BACKUPS" == *" $build_name "* ]]; then
        if [[ -e "$build_target" ]] && ! mv "$build_target" "$BUILD_QUARANTINE/failed-$build_name"; then
          restore_ok=0
          continue
        fi
        mv "$BUILD_QUARANTINE/$build_name" "$build_target" || restore_ok=0
      elif (( BUILD_ATTEMPTED )) && [[ -e "$build_target" ]]; then
        mv "$build_target" "$BUILD_QUARANTINE/failed-$build_name" || restore_ok=0
      fi
    done
    if (( restore_ok )); then
      echo "Build failed; previous build restored. Failed artifacts retained at $BUILD_QUARANTINE." >&2
    else
      echo "Build failed; rollback incomplete. Preserve and inspect $BUILD_QUARANTINE before retrying." >&2
    fi
  fi
  exit "$install_status"
}
trap restore_build_on_failure EXIT

usage() {
  cat <<'EOF'
Usage: ./scripts/install-ep51.sh [--mode local] [--dry-run] [--skip-deps] [--no-launch]

Preflights the sanitized EP 5.1 package, creates a local .env template, installs
dependencies when requested, builds the Console, and writes a local launch
manifest. Setup is build-only: services are always started separately. The
--no-launch flag explicitly records that choice. Dry-run makes no file changes.
It never imports production memory or enables JEV/cloud/RAG.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="${2:?missing mode}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-deps) SKIP_DEPS=1; shift ;;
    --no-launch) NO_LAUNCH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$MODE" == "local" ]] || { echo "Only --mode local is supported in EP 5.1." >&2; exit 2; }

run() {
  printf '+ %q' "$@"; printf '\n'
  (( DRY_RUN )) || "$@"
}

echo "EP 5.1 local deployment preflight: $ROOT"
if command -v zstd >/dev/null 2>&1; then
  echo "Optional zstd decoder: available (compressed source readback supported within configured limits)."
else
  echo "Optional zstd decoder: unavailable; plain JSONL remains supported, compressed sources stay explicitly unavailable. No automatic decoder installation."
fi
run python3 "$ROOT/scripts/release-preflight.py" --root "$ROOT" --json
run "$ROOT/scripts/verify-package.sh"
EP_VERSION="$(tr -d '\r\n' < "$ROOT/VERSION")"

if [[ ! -e "$ROOT/.env" ]]; then
  run cp "$ROOT/.env.example" "$ROOT/.env"
  (( DRY_RUN )) || chmod 600 "$ROOT/.env"
  echo "Created .env from .env.example; fill provider/database values before runtime use."
fi

if (( ! SKIP_DEPS )); then
  if command -v uv >/dev/null 2>&1 && [[ -f "$ROOT/api/pyproject.toml" ]]; then
    run uv sync --project "$ROOT/api"
  else
    echo "uv unavailable; skipped Python dependency install (use --skip-deps after provisioning)."
  fi
  if command -v npm >/dev/null 2>&1; then
    run npm ci --prefix "$ROOT"
  else
    echo "npm unavailable; cannot build the Console." >&2
    exit 1
  fi
fi

# Next.js can accidentally type-check a stale standalone tree as source. Keep
# the previous build recoverable but out of the source tree before rebuilding.
if (( DRY_RUN )); then
  BUILD_QUARANTINE='<temporary-build-backup-created-only-on-execution>'
else
  BUILD_QUARANTINE="$(mktemp -d "${TMPDIR:-/tmp}/ep51-build.XXXXXX")"
  BUILD_STARTED=1
fi
for build_name in client-dist standalone .next; do
  build_target="$(build_path "$build_name")"
  if [[ -e "$build_target" ]]; then
    (( DRY_RUN )) || BACKUP_MOVE_IN_PROGRESS="$build_name"
    run mv "$build_target" "$BUILD_QUARANTINE/$build_name"
    if (( ! DRY_RUN )); then
      COMPLETED_BACKUPS+="$build_name "
      BACKUP_MOVE_IN_PROGRESS=""
    fi
  fi
done

(( DRY_RUN )) || BUILD_ATTEMPTED=1
run npm run build --prefix "$ROOT/evolving-client"
run npm run build --prefix "$ROOT/console"

if (( ! DRY_RUN )); then
  mkdir -p "$ROOT/output"
  python3 - "$ROOT/output/ep51-local-launch.json" "$EP_VERSION" "$BUILD_QUARANTINE" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
path.write_text(json.dumps({
    "product": "Evolving Profile",
    "version": sys.argv[2],
    "mode": "local",
    "console_build": "verified",
    "provider_status": "not_checked",
    "external_rag_enabled": False,
    "jev_enabled": False,
    "cloud_backup_enabled": False,
    "launch": "manual",
    "services_started": False,
    "previous_build_backup": sys.argv[3],
    "boundary": "Sanitized package only; no production Bank, credentials, or receipts imported."
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  BUILD_VERIFIED=1
fi

if (( NO_LAUNCH )); then
  echo "EP $EP_VERSION package built and verified; service launch skipped (--no-launch)."
else
  echo "EP $EP_VERSION package built and verified. Services are NOT running: configure .env and start API/Console using api/README.md."
fi
