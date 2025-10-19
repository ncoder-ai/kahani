#!/bin/bash

# Kahani Backend Start Script

echo "🚀 Starting Kahani Backend..."

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Error: Virtual environment not found"
    echo "   Please run ./setup.sh first"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Start the server
echo "   Starting server on http://0.0.0.0:9876"
uvicorn app.main:app --host 0.0.0.0 --port 9876 --reload

