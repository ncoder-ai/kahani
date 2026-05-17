#!/usr/bin/env bash
# Poll the llama-server health endpoint until ready or timeout.
# Usage: wait_for_health.sh [url] [timeout_seconds]
set -euo pipefail

URL="${1:-http://localhost:5002/v1/models}"
TIMEOUT="${2:-60}"

echo "Waiting for $URL (up to ${TIMEOUT}s)..."
deadline=$(( $(date +%s) + TIMEOUT ))

while [[ $(date +%s) -lt $deadline ]]; do
  if curl -sf -o /dev/null -m 2 "$URL"; then
    echo "Server is up."
    exit 0
  fi
  sleep 2
done

echo "ERROR: server did not become healthy within ${TIMEOUT}s" >&2
exit 1
