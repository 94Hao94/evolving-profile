#!/bin/zsh
set -euo pipefail

EP_ROOT="${EP_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
EP_RUNTIME="${EP_RUNTIME:-python3}"

set -a
if [[ -f "${EP_ENV_FILE:-$HOME/.evolving-profile/profiles/evolving-profile-api.env}" ]]; then
  source "${EP_ENV_FILE:-$HOME/.evolving-profile/profiles/evolving-profile-api.env}"
fi
set +a

export PYTHONPATH="$EP_ROOT/api${PYTHONPATH:+:$PYTHONPATH}"
exec "$EP_RUNTIME" -m evolving_profile_api.main --host 127.0.0.1 --port 12088 --idle-timeout 0
