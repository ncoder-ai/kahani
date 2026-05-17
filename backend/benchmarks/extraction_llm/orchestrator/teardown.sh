#!/usr/bin/env bash
# Kill any llama-server process bound to the extraction port.
# Usage: teardown.sh [port]
set -euo pipefail

PORT="${1:-5002}"

PIDS=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)

if [[ -z "$PIDS" ]]; then
  echo "No process bound to port $PORT."
  exit 0
fi

echo "Killing llama-server PIDs on port $PORT: $PIDS"
kill $PIDS 2>/dev/null || true

# Give it 5s to exit cleanly
for _ in $(seq 1 5); do
  sleep 1
  REMAINING=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)
  [[ -z "$REMAINING" ]] && { echo "Stopped."; exit 0; }
done

# Force kill anything still there
REMAINING=$(lsof -ti tcp:"$PORT" 2>/dev/null || true)
if [[ -n "$REMAINING" ]]; then
  echo "Force-killing remaining: $REMAINING"
  kill -9 $REMAINING 2>/dev/null || true
fi

echo "Port $PORT freed."
