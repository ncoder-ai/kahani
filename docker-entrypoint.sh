#!/bin/bash
# Docker Entrypoint Script for Kahani

set -e

echo "🎭 Starting Kahani Docker Container..."

# Function to wait for service
wait_for_service() {
    local host=$1
    local port=$2
    local service_name=$3
    
    echo "⏳ Waiting for $service_name to be ready..."
    while ! nc -z $host $port; do
        sleep 1
    done
    echo "✅ $service_name is ready!"
}

# Create necessary directories
mkdir -p backend/data backend/logs frontend/logs

# Set proper permissions
chmod -R 755 backend/data backend/logs

# Run database migrations if needed
if [ ! -f "backend/data/kahani.db" ]; then
    echo "🗄️ Setting up database..."
    cd backend
    python migrate_add_auto_open_last_story.py || echo "Migration already applied or not needed"
    python migrate_add_prompt_templates.py || echo "Migration already applied or not needed"
    cd ..
    echo "✅ Database setup complete"
fi

# If PostgreSQL is configured, wait for it
if [[ "$DATABASE_URL" == postgresql* ]]; then
    # Extract host and port from DATABASE_URL if using PostgreSQL
    DB_HOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\):.*/\1/p' || echo "postgres")
    wait_for_service $DB_HOST 5432 "PostgreSQL"
fi

echo "🚀 Starting Kahani services..."

# Execute the main command
exec "$@"