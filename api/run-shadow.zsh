#!/bin/zsh
set -euo pipefail

EP_ROOT="/Users/example/Documents/Codex/2026-09-09/hind/work/evolving-profile"
EP_RUNTIME="/Users/example/.hindsight/runtimes/api-0.9.2/bin/python"

set -a
source /Users/example/.evolving-profile/profiles/evolving-profile-api.env
set +a

export PYTHONPATH="$EP_ROOT/api${PYTHONPATH:+:$PYTHONPATH}"
exec "$EP_RUNTIME" -m evolving_profile_api.main --host 127.0.0.1 --port 12088 --idle-timeout 0
