#!/usr/bin/env bash
# Run a Locust healthy-load profile against shop-demo (S2-B3).
#
#   bash experiments/load/run.sh
#   LOAD_PROFILE=smoke bash experiments/load/run.sh
#   make load PROFILE=standard HOST=http://192.168.100.10:30080
#
# Output goes to experiments/runs/load-<UTC stamp>/ (git-ignored). The script
# does not touch the cluster or Prometheus; it only sends HTTP requests.
set -euo pipefail

HOST="${HOST:-http://192.168.100.10:30080}"
PROFILE="${LOAD_PROFILE:-standard}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${OUT:-experiments/runs/load-$STAMP}"

mkdir -p "$OUT"

{
  echo "profile=$PROFILE"
  echo "host=$HOST"
  echo "started_utc=$STAMP"
  echo "commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
} >"$OUT/meta.txt"

echo "profile=$PROFILE host=$HOST output=$OUT"
LOAD_PROFILE="$PROFILE" uv run locust \
  -f experiments/load/locustfile.py \
  --headless \
  --host "$HOST" \
  --only-summary \
  --loglevel WARNING \
  --csv "$OUT/load"

echo "done: $OUT/load_stats.csv"
