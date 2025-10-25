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

# Handle ownership for user 1000:1000 (Docker user mapping)
echo "🔧 Ensuring proper ownership for user 1000:1000..."
echo "  - Current user: $(id -u):$(id -g)"
echo "  - Target user: 1000:1000"

# Fix ownership of mounted volumes (run as root to have permission to change ownership)
if [ "$(id -u)" = "0" ]; then
    echo "🔧 Running as root - fixing ownership of mounted volumes..."
    chown -R 1000:1000 /app/data 2>/dev/null && echo "✅ Fixed data directory ownership" || echo "⚠️  Could not change data directory ownership"
    chown -R 1000:1000 /app/logs 2>/dev/null && echo "✅ Fixed logs directory ownership" || echo "⚠️  Could not change logs directory ownership"
    
    # Set permissions after ownership change
    chmod -R 755 /app/data 2>/dev/null && echo "✅ Set data directory permissions" || echo "⚠️  Could not set data directory permissions"
    chmod -R 755 /app/logs 2>/dev/null && echo "✅ Set logs directory permissions" || echo "⚠️  Could not set logs directory permissions"
    
    # Switch to user 1000:1000 for the application
    echo "🔧 Switching to user 1000:1000 for application..."
    exec gosu 1000:1000 "$@"
else
    # If not running as root, try to fix ownership with current user
    echo "🔧 Not running as root - attempting to fix ownership with current user..."
    chown -R 1000:1000 /app/data 2>/dev/null && echo "✅ Fixed data directory ownership" || echo "⚠️  Could not change data directory ownership"
    chown -R 1000:1000 /app/logs 2>/dev/null && echo "✅ Fixed logs directory ownership" || echo "⚠️  Could not change logs directory ownership"
    
    chmod -R 755 /app/data 2>/dev/null && echo "✅ Set data directory permissions" || echo "⚠️  Could not set data directory permissions"
    chmod -R 755 /app/logs 2>/dev/null && echo "✅ Set logs directory permissions" || echo "⚠️  Could not set logs directory permissions"
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

# Initialize database if needed (must run BEFORE Alembic migrations)
if [[ "$DATABASE_URL" == sqlite* ]]; then
    echo "🗄️ Checking SQLite database..."
    cd /app
    
    # Check if database exists and is valid
    if [ ! -f "/app/data/kahani.db" ]; then
        echo "🗄️ Database does not exist - initializing..."
    else
        echo "🔍 Database exists - checking integrity..."
        # Test if database is accessible and has tables
        python -c "
import sqlite3
try:
    conn = sqlite3.connect('/app/data/kahani.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')
    tables = cursor.fetchall()
    conn.close()
    if not tables:
        print('⚠️  Database exists but is empty - will reinitialize')
        import os
        os.remove('/app/data/kahani.db')
        exit(1)
    else:
        print('✅ Database is valid and contains tables')
except Exception as e:
    print(f'⚠️  Database is corrupted: {e} - will reinitialize')
    import os
    os.remove('/app/data/kahani.db')
    exit(1)
" || {
            echo "🗄️ Reinitializing database..."
        }
    fi
    
    # Run database initialization (creates tables if DB is new)
    if [ -f "init_database.py" ]; then
        echo "Running database initialization..."
        python init_database.py || echo "⚠️  Database initialization warning"
    fi
    
    echo "✅ Database initialization complete"
    echo "🔐 First user to register will become admin automatically"
else
    echo "✅ Using non-SQLite database - skipping initialization"
fi

# Run Alembic migrations AFTER database initialization
echo "🗄️ Running Alembic migrations to upgrade schema..."
alembic upgrade head || echo "⚠️ Alembic migration failed"

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