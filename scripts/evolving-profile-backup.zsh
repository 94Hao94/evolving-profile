#!/bin/zsh
set -euo pipefail

export PATH="${EVOLVING_PROFILE_PG_BIN:-/usr/local/bin}:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

STATE_ROOT="${EVOLVING_PROFILE_STATE_ROOT:-$HOME/.evolving-profile}"
PROFILE_ENV="$STATE_ROOT/profiles/evolving-profile-api.env"
BACKUP_ROOT="${EVOLVING_PROFILE_BACKUP_ROOT:-$STATE_ROOT/backups/managed}"
SETTINGS_PATH="$STATE_ROOT/config/backup-settings.json"
KEYCHAIN_SERVICE="evolving-profile-backup-key-v1"
KEYCHAIN_ACCOUNT="$USER"
MODE="${1:-daily}"
DRY_RUN=0
[[ "${2:-}" == "--dry-run" || "$MODE" == "--dry-run" ]] && DRY_RUN=1
[[ "$MODE" == "--dry-run" ]] && MODE="daily"
[[ "$MODE" == "daily" || "$MODE" == "weekly" || "$MODE" == "monthly" ]] || { print -u2 "mode must be daily, weekly, or monthly"; exit 2; }

RETENTION_DAYS=14
MAX_SETS=14
INCLUDE_DATABASE=1
INCLUDE_CONFIG=1
INCLUDE_CAPTURE=1
VERIFY_CHECKSUM=1
if [[ -r "$SETTINGS_PATH" ]]; then
  BACKUP_ROOT="$(jq -r '.local.root // empty' "$SETTINGS_PATH")"
  RETENTION_DAYS="$(jq -r '.local.retention_days // 14' "$SETTINGS_PATH")"
  MAX_SETS="$(jq -r '.local.max_sets // 14' "$SETTINGS_PATH")"
  INCLUDE_DATABASE="$(jq -r 'if .local.database == false then 0 else 1 end' "$SETTINGS_PATH")"
  INCLUDE_CONFIG="$(jq -r 'if .local.config == false then 0 else 1 end' "$SETTINGS_PATH")"
  INCLUDE_CAPTURE="$(jq -r 'if .local.capture == false then 0 else 1 end' "$SETTINGS_PATH")"
  VERIFY_CHECKSUM="$(jq -r 'if .local.verify_checksum == false then 0 else 1 end' "$SETTINGS_PATH")"
  [[ -n "$BACKUP_ROOT" ]] || BACKUP_ROOT="$STATE_ROOT/backups/managed"
fi

[[ -r "$PROFILE_ENV" ]] || { print -u2 "Evolving Profile profile missing"; exit 1; }
set -a
source "$PROFILE_ENV"
set +a

db_url="${EVOLVING_PROFILE_API_DATABASE_URL:?database URL missing}"
timestamp=$(date '+%Y%m%d-%H%M%S')
target="$BACKUP_ROOT/$MODE"
lock_dir="$STATE_ROOT/codex/state/backup-$MODE.lock"
mkdir -p "$target" "${lock_dir:h}"
chmod 700 "$BACKUP_ROOT" "$target"
if ! mkdir "$lock_dir" 2>/dev/null; then print -r -- '{"status":"already-running"}'; exit 0; fi
key_file=""
cleanup() { [[ -n "$key_file" ]] && rm -f "$key_file"; rmdir "$lock_dir" 2>/dev/null || true; }
backup_receipt() {
  local code=$?
  if (( ! DRY_RUN )); then
    local state="completed" reason="backup_ok" detail="本地备份完成"
    if (( code != 0 )); then state="failed"; reason="backup_exit_$code"; detail="备份流程退出码 $code，详情请核对备份任务日志"; fi
    jq -cn --arg at "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" --arg status "$state" --arg code "$reason" --arg detail "$detail" \
      '{at:$at,status:$status,code:$code,detail:$detail}' >> "$STATE_ROOT/logs/backup-run-receipts.jsonl" 2>/dev/null || true
  fi
  cleanup
}
trap backup_receipt EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if (( DRY_RUN )); then
  # Do not expose credentials embedded in a database URL through launchd logs.
  jq -n --arg mode "$MODE" --arg target "$target" --argjson database "$INCLUDE_DATABASE" --argjson config "$INCLUDE_CONFIG" --argjson capture "$INCLUDE_CAPTURE" --argjson checksum "$VERIFY_CHECKSUM" '{status:"dry-run",mode:$mode,target:$target,artifacts:{database:($database==1),config:($config==1),capture:($capture==1),verify_checksum:($checksum==1)}}'
  exit 0
fi

if ! security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "$KEYCHAIN_SERVICE" -w >/dev/null 2>&1; then
  security add-generic-password -U -a "$KEYCHAIN_ACCOUNT" -s "$KEYCHAIN_SERVICE" -w "$(openssl rand -base64 48)" >/dev/null
fi
key_file=$(mktemp "${TMPDIR:-/tmp}/evolving-profile-backup-key.XXXXXX")
chmod 600 "$key_file"
security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "$KEYCHAIN_SERVICE" -w > "$key_file"

db_partial="$target/evolving-profile-db-${timestamp}.partial.dump"
db_final="$target/evolving-profile-db-${timestamp}.dump"
config_archive="$target/evolving-profile-config-${timestamp}.tar.gz"
capture_db="$STATE_ROOT/memory-os/capture/capture.sqlite3"
capture_partial="$target/evolving-profile-capture-${timestamp}.partial.sqlite"
capture_compressed="$target/evolving-profile-capture-${timestamp}.sqlite.gz"
capture_encrypted="$target/evolving-profile-capture-${timestamp}.sqlite.gz.enc"
if (( INCLUDE_DATABASE )); then
  pg_dump --format=custom --file "$db_partial" "$db_url"
  (( ! VERIFY_CHECKSUM )) || pg_restore --list "$db_partial" >/dev/null
  mv "$db_partial" "$db_final"
fi

# SQLite's online backup API produces a consistent copy even when Hooks append
# new evidence. The compressed encrypted snapshot is intentionally separate
# from the configuration tar so it can be restored and integrity-checked alone.
if (( INCLUDE_CAPTURE )) && [[ -f "$capture_db" ]]; then
  sqlite3 "$capture_db" ".backup '$capture_partial'"
  [[ "$(sqlite3 "$capture_partial" 'PRAGMA integrity_check;')" == "ok" ]]
  gzip -c "$capture_partial" > "$capture_compressed"
  openssl enc -aes-256-cbc -salt -pbkdf2 -iter 600000 -md sha256 -in "$capture_compressed" -out "$capture_encrypted" -pass "file:$key_file"
  capture_restore=$(mktemp "${TMPDIR:-/tmp}/evolving-profile-capture-restore.XXXXXX.gz")
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -in "$capture_encrypted" -out "$capture_restore" -pass "file:$key_file"
  capture_check=$(mktemp "${TMPDIR:-/tmp}/evolving-profile-capture-check.XXXXXX.sqlite")
  gzip -dc "$capture_restore" > "$capture_check"
  [[ "$(sqlite3 "$capture_check" 'PRAGMA integrity_check;')" == "ok" ]]
  rm -f "$capture_partial" "$capture_compressed" "$capture_restore" "$capture_check"
fi

inputs=(
  "$STATE_ROOT/codex.json"
  "$STATE_ROOT/memory-contract-v5.json"
  "$STATE_ROOT/memory-access-policy-v3.json"
  "$STATE_ROOT/audit"
  "$STATE_ROOT/catalog"
  "$STATE_ROOT/task-state"
  "$STATE_ROOT/memory-os/capture/tool-response-archive"
  "$STATE_ROOT/profiles"
  "$STATE_ROOT/guidance-v1"
  "$STATE_ROOT/bin"
  "$STATE_ROOT/runtime/guidance"
  "$STATE_ROOT/runtime/host-adapter"
  "$STATE_ROOT/runtime/status"
  "$STATE_ROOT/claude-code"
  "$STATE_ROOT/control-plane"
  "$HOME/.codex/config.toml"
  "$HOME/.codex/hooks.json"
  "$HOME/.claude/settings.json"
  "$HOME/.claude.json"
  "$HOME/.hermes/config.yaml"
  "$HOME/Library/LaunchAgents/com.evolving-profile.api-shadow.plist"
  "$HOME/Library/LaunchAgents/com.evolving-profile.query-controller-shadow.plist"
  "$HOME/Library/LaunchAgents/com.evolving-profile.status-shadow.plist"
  "$HOME/Library/LaunchAgents/com.evolving-profile.shadow.plist"
  "$HOME/Library/LaunchAgents/com.evolving-profile.backup.plist"
  "$HOME/Library/LaunchAgents/com.evolving-profile.guidance-worker.plist"
  "$HOME/Library/LaunchAgents/com.evolving-profile.topic-catalog.plist"
  "$HOME/Library/LaunchAgents/com.evolving-profile.worker.plist"
  "$HOME/Library/LaunchAgents/com.evolving-profile.postgres.plist"
)
existing=()
for item in "${inputs[@]}"; do [[ -e "$item" ]] && existing+=("$item"); done
if (( INCLUDE_CONFIG )); then
  ((${#existing[@]})) || { print -u2 "no configuration inputs found"; exit 1; }
  tar -czf "$config_archive" "${existing[@]}"
fi

encrypted="$target/evolving-profile-config-${timestamp}.tar.gz.enc"
if (( INCLUDE_CONFIG )); then
  openssl enc -aes-256-cbc -salt -pbkdf2 -iter 600000 -md sha256 -in "$config_archive" -out "$encrypted" -pass "file:$key_file"
  if (( VERIFY_CHECKSUM )); then
    restored=$(mktemp "${TMPDIR:-/tmp}/evolving-profile-restore-verify.XXXXXX")
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -in "$encrypted" -out "$restored" -pass "file:$key_file"
    cmp -s "$config_archive" "$restored"
    rm -f "$restored"
  fi
  rm -f "$config_archive"
fi
backup_outputs=()
(( ! INCLUDE_DATABASE )) || backup_outputs+=("$db_final")
(( ! INCLUDE_CONFIG )) || backup_outputs+=("$encrypted")
[[ -f "$capture_encrypted" ]] && backup_outputs+=("$capture_encrypted")
(( ${#backup_outputs} )) || { print -u2 "selected backup artifacts produced no files"; exit 1; }
if (( VERIFY_CHECKSUM )); then
  chmod 600 "${backup_outputs[@]}"
  (cd "$target" && shasum -a 256 ${backup_outputs:t} > "SHA256SUMS-${timestamp}")
else
  chmod 600 "${backup_outputs[@]}"
fi

case "$MODE" in
  daily) find "$target" -type f -mtime +"$RETENTION_DAYS" -delete ;;
  weekly) find "$target" -type f -mtime +84 -delete ;;
  monthly) find "$target" -type f -mtime +365 -delete ;;
esac
# Enforce the configured maximum by backup timestamp, regardless of which
# selected artifact types produced the set.
stamps=("${(@f)$(find "$target" -maxdepth 1 -type f -name 'evolving-profile-*' -print | sed -E 's/.*-([0-9]{8}-[0-9]{6})\..*/\1/' | sort -r -u)}")
if (( ${#stamps} > MAX_SETS )); then
  for stamp_old in "${stamps[$((MAX_SETS + 1)),-1]}"; do
    rm -f "$target"/*-"$stamp_old".* "$target"/SHA256SUMS-"$stamp_old"
  done
fi
jq -n --arg mode "$MODE" --arg db "$db_final" --arg encrypted "$encrypted" --arg capture "$capture_encrypted" '{status:"completed",mode:$mode,database_backup:$db,encrypted_config_backup:$encrypted,capture_backup:($capture|select(length>0)),encryption:"AES-256-CBC+PBKDF2-SHA256(iter=600000)",model_called:false}'
