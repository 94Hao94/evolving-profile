#!/bin/zsh
set -euo pipefail

EP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EP_RUNTIME="${EP_RUNTIME_PYTHON:-python3}"

set -a
source "${EVOLVING_PROFILE_ENV_FILE:-$HOME/.evolving-profile/profiles/evolving-profile-api.env}"
set +a

export PYTHONPATH="$EP_ROOT/api${PYTHONPATH:+:$PYTHONPATH}"
exec "$EP_RUNTIME" -m evolving_profile_api.main --host 127.0.0.1 --port 12088 --idle-timeout 0
