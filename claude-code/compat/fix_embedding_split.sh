#!/bin/zsh
# Make the API (read path) embed with the same model as the worker (write path) by neutralising the embedding override.
#
#   zsh fix_embedding_split.sh status      what model the API would load, and what the worker uses
#   zsh fix_embedding_split.sh apply       backup + comment out the EMBEDDINGS_* lines in config/retrieval-models.env
#   zsh fix_embedding_split.sh rollback    restore the newest backup
#   DIR=/some/copy zsh fix_embedding_split.sh apply      (test against a copy; DIR must contain retrieval-models.env)
#
# After `apply` the API must be restarted for it to take effect (launchd restarts it):
#   launchctl kickstart -k gui/$(id -u)/com.evolving-profile.api-shadow
# Then verify:  python .../compat/ep_desktop_health.py   -> "embedding model consistency  OK"
set -e
DIR=${DIR:-$HOME/.evolving-profile/config}
F=$DIR/retrieval-models.env
PROFILE=${PROFILE:-$HOME/.evolving-profile/profiles/evolving-profile-api.env}
[[ -f "$F" ]] || { echo "ABORT: $F not found"; exit 1 }

effective() {   # what the API launcher would end up with: profile first, then the overlay on top (same order as evolving-profile-api-shadow.zsh)
  ( set -a; source "$PROFILE"; [[ -r "$F" ]] && source "$F"; set +a
    echo "  API would load  : ${EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_MODEL_ID}  (dim ${EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_DIMENSIONS})" )
  ( set -a; source "$PROFILE"; set +a
    echo "  worker loads    : ${EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_MODEL_ID}  (the worker launcher does not read the overlay)" )
}

case "${1:-status}" in
  status) effective ;;
  apply)
    if ! grep -q '^EVOLVING_PROFILE_API_EMBEDDINGS_' "$F"; then echo "already applied (no active EMBEDDINGS_ lines)"; effective; exit 0; fi
    TS=$(date +%Y%m%d%H%M%S)
    cp -p "$F" "$F.bak-$TS"
    sed -i '' 's/^\(EVOLVING_PROFILE_API_EMBEDDINGS_\)/# disabled-by-embedding-fix-'$TS' \1/' "$F"
    echo "backup: $F.bak-$TS"; echo "after apply:"; effective
    echo "NOW restart the API:  launchctl kickstart -k gui/\$(id -u)/com.evolving-profile.api-shadow" ;;
  rollback)
    B=$(ls -t "$F".bak-* 2>/dev/null | head -n 1); [[ -n "$B" ]] || { echo "no backup found"; exit 1 }
    cp -p "$B" "$F"; echo "restored from $B"; effective ;;
  *) echo "usage: $0 status|apply|rollback"; exit 2 ;;
esac
