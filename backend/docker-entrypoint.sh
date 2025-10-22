#!/bin/bash
# Docker Entrypoint Script for Kahani

set -e

echo "🎭 Starting Kahani Docker Container..."

# Function to wait for service
wait_for_service() {
    local host=$1
    local port=$2
    local service_name=$3
    local max_attempts=${4:-30}
    local attempt=0
    
    echo "⏳ Waiting for $service_name to be ready..."
    while ! nc -z $host $port 2>/dev/null; do
        attempt=$((attempt+1))
        if [ $attempt -ge $max_attempts ]; then
            echo "❌ Failed to connect to $service_name after $max_attempts attempts"
            return 1
        fi
        sleep 1
    done
    echo "✅ $service_name is ready!"
    return 0
}

# Create necessary directories (only if we have permission)
echo "📁 Creating directories..."
mkdir -p /app/data /app/data/audio /app/logs 2>/dev/null || echo "⚠️  Some directories could not be created (mounted volumes)"
mkdir -p /app/exports /app/backups 2>/dev/null || echo "⚠️  Some directories could not be created (mounted volumes)"

# Fix permissions for mounted volumes (critical for Docker volume mounts)
echo "🔧 Setting up permissions for mounted volumes..."
# Try to fix permissions, but don't fail if we can't
chmod -R 755 /app/data 2>/dev/null || echo "⚠️  Could not set data directory permissions (mounted volume)"
chmod -R 755 /app/logs 2>/dev/null || echo "⚠️  Could not set logs directory permissions (mounted volume)"
chmod -R 755 /app/exports /app/backups 2>/dev/null || echo "⚠️  Could not set export/backup permissions"

# If we still can't write to data directory, try to fix ownership
if [ ! -w /app/data ]; then
    echo "🔧 Attempting to fix data directory ownership..."
    # Try to change ownership to the current user
    chown -R $(id -u):$(id -g) /app/data 2>/dev/null || echo "⚠️  Could not change data directory ownership"
    chmod -R 755 /app/data 2>/dev/null || echo "⚠️  Could not set data directory permissions after ownership change"
fi

# Ensure data directory is writable by the application (critical for SQLite)
echo "🗄️  Ensuring data directory is writable..."
touch /app/data/.test_write 2>/dev/null && rm -f /app/data/.test_write && echo "✅ Data directory is writable" || echo "❌ Data directory is not writable - database will fail!"

# Ensure logs directory is writable by the application
echo "📝 Ensuring logs directory is writable..."
touch /app/logs/.test_write 2>/dev/null && rm -f /app/logs/.test_write && echo "✅ Logs directory is writable" || echo "⚠️  Logs directory may not be writable, will use console logging"

# If PostgreSQL is configured, wait for it
if [[ "$DATABASE_URL" == postgresql* ]]; then
    echo "🐘 PostgreSQL database detected"
    # Extract host and port from DATABASE_URL
    DB_HOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\):.*/\1/p' || echo "postgres")
    DB_PORT=$(echo $DATABASE_URL | sed -n 's/.*:\([0-9]*\)\/.*/\1/p' || echo "5432")
    
    wait_for_service $DB_HOST $DB_PORT "PostgreSQL" 60
    
    # Give PostgreSQL a bit more time to fully initialize
    sleep 2
fi

# Initialize database if needed
if [ ! -f "/app/data/kahani.db" ] && [[ "$DATABASE_URL" == sqlite* ]]; then
    echo "🗄️ Initializing SQLite database with admin system..."
    cd /app
    
    # Run database initialization with admin system
    if [ -f "init_database.py" ]; then
        echo "Running database initialization with admin system..."
        python init_database.py || echo "⚠️  Database initialization warning (may already exist)"
    fi
    
    echo "✅ Database initialization complete"
    echo "🔐 First user to register will become admin automatically"
else
    echo "✅ Database already exists"
fi

# Check for TTS provider availability (optional)
if [ ! -z "$TTS_API_URL" ]; then
    echo "🔊 TTS provider configured at: $TTS_API_URL"
    # Extract host and port for health check (optional, non-blocking)
    TTS_HOST=$(echo $TTS_API_URL | sed -n 's|.*//\([^:]*\).*|\1|p')
    TTS_PORT=$(echo $TTS_API_URL | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
    
    if [ ! -z "$TTS_HOST" ] && [ ! -z "$TTS_PORT" ]; then
        echo "⏳ Checking TTS provider availability (non-blocking)..."
        if wait_for_service $TTS_HOST $TTS_PORT "TTS Provider" 10; then
            echo "✅ TTS provider is available"
        else
            echo "⚠️  TTS provider not available, can be configured later via Settings UI"
        fi
    fi
else
    echo "ℹ️  TTS not pre-configured, can be set up via Settings UI"
fi

echo "🚀 Starting Kahani application..."

# Execute the main command
exec "$@"