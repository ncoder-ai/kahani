#!/bin/bash
# Fix permissions for Docker volume mounts

echo "🔧 Fixing permissions for Docker volume mounts..."

# Create directories if they don't exist
mkdir -p ./backend/data
mkdir -p ./backend/logs

# Set proper permissions for Docker volumes
echo "📁 Setting permissions for data directory..."
chmod -R 755 ./backend/data

echo "📁 Setting permissions for logs directory..."
chmod -R 755 ./backend/logs

# Show current permissions
echo "📊 Current permissions:"
ls -la ./backend/ | grep -E "(data|logs)"

echo "✅ Permissions fixed. You can now run 'docker compose up'"
