#!/bin/zsh
# read the EP database with the profile's own credentials:  epsql.sh "select ..."   (or pipe SQL on stdin)
export PATH="$HOME/.pg0/installation/18.1.0/bin:/usr/bin:/bin"
set -a; source "$HOME/.evolving-profile/profiles/evolving-profile-api.env"; set +a
URL="${EVOLVING_PROFILE_API_DATABASE_URL}"
if [[ -n "$1" ]]; then psql "$URL" -X -A -F '|' -P pager=off -c "$1"; else psql "$URL" -X -A -F '|' -P pager=off; fi
