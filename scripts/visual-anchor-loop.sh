#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/output/playwright/anchor-loop"
mkdir -p "$OUT"
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PWCLI="${PWCLI:-$CODEX_HOME/skills/playwright/scripts/playwright_cli.sh}"
URL="${1:-}"
if [[ -z "$URL" ]]; then
  CONSOLE_ORIGIN="${EVOLVING_PROFILE_CONSOLE_URL:-http://127.0.0.1:9999}"
  BANK_PATH="$(curl --fail --silent --show-error "$CONSOLE_ORIGIN/api/evolving-profile/bank-selection" | node -e '
    let input=""; process.stdin.on("data",chunk=>input+=chunk); process.stdin.on("end",()=>{
      const result=JSON.parse(input);
      if(result.status!=="ready" || !result.selected_bank_id) { console.error("Primary bank is not verified; pass an explicit valid URL."); process.exit(1); }
      process.stdout.write(encodeURIComponent(result.selected_bank_id));
    });')"
  URL="$CONSOLE_ORIGIN/zh-CN/banks/$BANK_PATH?view=flow"
fi

for round in 1 2 3 4 5; do
  "$PWCLI" open "${URL}&anchor_round=${round}" >/dev/null
  sleep 2
  "$PWCLI" run-code 'const first = page.locator("aside button").first(); if (await first.count()) { await first.click(); await page.waitForTimeout(2500); }' >/dev/null 2>&1 || true
  "$PWCLI" screenshot --filename="$OUT/round-${round}.png" >/dev/null
  "$PWCLI" snapshot > "$OUT/round-${round}.yml"
  printf 'round=%s screenshot=%s snapshot=%s\n' "$round" "$OUT/round-${round}.png" "$OUT/round-${round}.yml"
done

printf 'visual loop complete: 5 settled browser captures written to %s\n' "$OUT"
