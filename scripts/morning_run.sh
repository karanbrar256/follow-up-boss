#!/usr/bin/env bash
# Build today's sheet from live Follow Up Boss data (read-only).
# Usage: scripts/morning_run.sh [office|shift|minimum]
# Needs FOLLOW_UP_BOSS_API_KEY in the environment and network access to
# api.followupboss.com. Output goes to reports/ (git-ignored: it holds client info).
set -euo pipefail
cd "$(dirname "$0")/.."
DAY="${1:-${DAY_TYPE:-office}}"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
pip install -q -e . >/dev/null
mkdir -p reports
OUT="reports/$(TZ=America/Vancouver date +%F)-${DAY}.md"
FUB_TOOLKIT_ALLOW_LIVE=1 python -m fub_toolkit --source live daily --day "$DAY" --out "$OUT"
echo "$OUT"
