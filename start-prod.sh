#!/bin/bash
# Production startup script for Docker container
# Starts both backend and frontend with correct ports

set -e

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
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID

