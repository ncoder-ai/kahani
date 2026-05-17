#!/bin/sh
# Custom Next.js start script with logging enabled
# This ensures Docker containers have proper log output

set -e

# Get port from environment or use default
PORT="${PORT:-6789}"
HOSTNAME="${HOSTNAME:-0.0.0.0}"

# Enable Node.js logging
export NODE_ENV=production

# Log startup information
echo "=========================================="
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting Next.js server..."
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Port: $PORT"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Hostname: $HOSTNAME"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Node version: $(node --version)"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] NPM version: $(npm --version)"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Next.js starting..."
echo "=========================================="

# Start Next.js with explicit hostname and port
# Use --hostname flag to bind to 0.0.0.0 (required for Docker)
# Next.js will output request logs automatically
exec node_modules/.bin/next start \
  --hostname "$HOSTNAME" \
  --port "$PORT"
