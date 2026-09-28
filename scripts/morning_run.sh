#!/usr/bin/env bash
# Build today's sheet from live Follow Up Boss data (read-only).
# Usage:
#   scripts/morning_run.sh [office|shift|minimum]
#   scripts/morning_run.sh auto path/to/todays_calendar_events.json
#     (auto: a "BCLDB Shift" event today -> shift; added <24h before -> minimum)
# Needs network access to api.followupboss.com and the FUB credential.
# Output goes to reports/ (git-ignored: it holds client info).
set -euo pipefail
cd "$(dirname "$0")/.."
DAY="${1:-${DAY_TYPE:-office}}"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
pip install -q -e . >/dev/null
if [ "$DAY" = "auto" ]; then
  EVENTS="${2:-}"
  if [ -n "$EVENTS" ] && [ -f "$EVENTS" ]; then
    DAY="$(python -m fub_toolkit daytype --events "$EVENTS")"
  else
    DAY="office"
  fi
fi
mkdir -p reports
OUT="reports/$(TZ=America/Vancouver date +%F)-${DAY}.md"
FUB_TOOLKIT_ALLOW_LIVE=1 python -m fub_toolkit --source live daily --day "$DAY" --out "$OUT" >/dev/null
echo "$OUT"
