#!/bin/bash
# Startup script for Kahani backend

set -e

echo "🎭 Starting Kahani Backend..."

# Create directories if they don't exist
mkdir -p /app/data /app/logs /app/exports /app/backups

# Set permissions for directories
chmod -R 755 /app/data /app/logs /app/exports /app/backups 2>/dev/null || true

# Try to fix ownership if we can't write
if [ ! -w /app/data ]; then
    echo "🔧 Fixing data directory permissions..."
    chown -R $(id -u):$(id -g) /app/data 2>/dev/null || true
    chmod -R 755 /app/data 2>/dev/null || true
fi

# Test if we can write to data directory
if [ ! -w /app/data ]; then
    echo "❌ WARNING: Cannot write to data directory /app/data"
    echo "   This may cause database initialization to fail."
    echo "   Check Docker volume permissions."
else
    echo "✅ Data directory is writable"
fi

# Run the main application
exec "$@"