#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_ROOT="${EVOLVING_PROFILE_STATE_ROOT:-$HOME/.evolving-profile}"
PLIST="$HOME/Library/LaunchAgents/com.evolving-profile.backup.plist"
SCRIPT="$STATE_ROOT/bin/evolving-profile-backup.zsh"
SETTINGS="$STATE_ROOT/config/backup-settings.json"

install -d -m 700 "$STATE_ROOT/bin" "$STATE_ROOT/config" "$STATE_ROOT/backups/managed"
install -m 700 "$ROOT/scripts/evolving-profile-backup.zsh" "$SCRIPT"
if [[ ! -e "$SETTINGS" ]]; then
  sed "s|REPLACE_WITH_A_DEDICATED_BACKUP_DIRECTORY|$STATE_ROOT/backups/managed|" \
    "$ROOT/config/backup-settings.example.json" > "$SETTINGS"
  chmod 600 "$SETTINGS"
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.evolving-profile.backup</string>
  <key>ProgramArguments</key><array><string>$SCRIPT</string><string>daily</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>25</integer></dict>
  <key>StandardOutPath</key><string>$STATE_ROOT/logs/backup.log</string>
  <key>StandardErrorPath</key><string>$STATE_ROOT/logs/backup.error.log</string>
</dict></plist>
EOF
chmod 600 "$PLIST"
launchctl bootout "gui/$(id -u)/com.evolving-profile.backup" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
printf 'Installed backup task: %s\n' "$PLIST"
