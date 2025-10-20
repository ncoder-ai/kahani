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

# Check and download AI models if needed
MODEL_CACHE="$HOME/.cache/torch/sentence_transformers/"
if [[ ! -d "$MODEL_CACHE" ]] || [[ $(find "$MODEL_CACHE" -type f | wc -l) -lt 10 ]]; then
    echo "📦 Downloading AI models (one-time setup)..."
    python download_models.py || echo "⚠️  Model download failed, will try at runtime"
else
    echo "✅ AI models already cached"
fi

# Start the server
echo "   Starting server on http://0.0.0.0:9876"
uvicorn app.main:app --host 0.0.0.0 --port 9876 --reload

