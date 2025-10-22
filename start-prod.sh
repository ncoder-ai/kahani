#!/bin/bash
# Production startup script for Docker container
# ⚠️  THIS SCRIPT IS FOR DOCKER CONTAINERS ONLY ⚠️
# For bare-metal/development, use: ./start-dev.sh
#
# Starts both backend and frontend with correct ports

set -e

# Check if we're inside a Docker container
if [ ! -d "/app/backend" ]; then
    echo "❌ ERROR: This script is designed to run inside a Docker container"
    echo ""
    echo "📍 You're trying to run it on bare-metal (your local machine)"
    echo ""
    echo "✅ For local development, use:"
    echo "   ./start-dev.sh"
    echo ""
    echo "🐳 For production (Docker), use:"
    echo "   docker build -t kahani ."
    echo "   docker run -p 9876:9876 -p 6789:6789 kahani"
    echo ""
    exit 1
fi

echo "🚀 Starting Kahani Production Services..."

# Start backend on port 9876 (in background)
cd /app/backend
echo "📡 Starting backend on port 9876..."
uvicorn app.main:app --host 0.0.0.0 --port 9876 &
BACKEND_PID=$!

# Give backend time to start
sleep 3

# Start frontend on port 6789
cd /app/frontend
echo "🎨 Starting frontend on port 6789..."
PORT=6789 npm start &
FRONTEND_PID=$!

echo "✅ Kahani is running!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📖 Frontend:     http://localhost:6789"
echo "📡 Backend API:  http://localhost:9876"
echo "📚 API Docs:     http://localhost:9876/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🔐 First user to register becomes admin automatically"
echo "💡 No default users - register your first account to get started"
echo ""
echo "⚠️  Make sure your LLM service is configured in Settings"
echo "   (default: http://localhost:1234 for LM Studio)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID

