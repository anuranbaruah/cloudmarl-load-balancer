#!/usr/bin/env bash
# Runs random, round-robin and MARL routing for the same duration and load,
# then prints the comparison.  (Windows: run from Git Bash or WSL.)
#
# Usage:  ./experiments/run_experiment.sh [seconds_per_mode] [rate_per_region]
set -euo pipefail
cd "$(dirname "$0")/.."

DURATION=${1:-180}
RATE=${2:-17}
LBS="lb-mumbai lb-singapore lb-frankfurt lb-virginia"
PY=$(command -v python3 || command -v python)

echo "== Starting / updating base services =="
docker compose up -d --build db cloud grafana vm-xl vm-l vm-m vm-s1 vm-s2
echo "Waiting for the cloud API..."
until curl -s http://localhost:8000/health >/dev/null; do sleep 2; done

echo "== Clearing old results =="
curl -s -X POST http://localhost:8000/reset; echo

for MODE in random rr marl; do
  echo "== Running MODE=$MODE for ${DURATION}s (RATE ${RATE}/s per region) =="
  MODE=$MODE RATE=$RATE docker compose up -d --force-recreate $LBS
  sleep "$DURATION"
  docker compose stop $LBS
  sleep 5            # let worker queues drain before the next policy
done

echo "== Results =="
"$PY" experiments/analyze.py

# leave the system running in MARL mode for the dashboard / demo
MODE=marl RATE=$RATE docker compose up -d $LBS >/dev/null
