#!/bin/bash
# Start Kahani Backend Server

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [[ ! -d ".venv" ]]; then
    echo -e "${RED}Error: Virtual environment not found!${NC}"
    echo "Please run ./install.sh first"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check and download AI models if needed
MODEL_CACHE="$HOME/.cache/torch/sentence_transformers/"
if [[ ! -d "$MODEL_CACHE" ]] || [[ $(find "$MODEL_CACHE" -type f | wc -l) -lt 10 ]]; then
    echo -e "${BLUE}📦 Downloading AI models (one-time setup)...${NC}"
    cd backend
    python download_models.py || echo -e "${RED}⚠️  Model download failed, will try at runtime${NC}"
    cd "$SCRIPT_DIR"
else
    echo -e "${GREEN}✅ AI models already cached${NC}"
fi

# Load environment variables from .env file at project root
if [[ -f .env ]]; then
    echo -e "${BLUE}Loading .env...${NC}"
    set -a
    source .env
    set +a
fi

# Load configuration from config.yaml
if [[ -f config.yaml ]]; then
    export BACKEND_PORT=$(grep -A 2 'backend:' config.yaml | grep 'port:' | grep -o '[0-9]*')
    export BACKEND_HOST=$(grep -A 2 'backend:' config.yaml | grep 'host:' | awk '{print $2}')
fi

# Set defaults if not provided
export PYTHONPATH="${SCRIPT_DIR}/backend"
export PORT="${BACKEND_PORT:-9876}"
export HOST="${BACKEND_HOST:-0.0.0.0}"
export HOST="${HOST:-0.0.0.0}"

echo -e "${GREEN}Starting Kahani Backend Server...${NC}"
echo -e "${BLUE}Port:${NC} $PORT"
echo -e "${BLUE}Host:${NC} $HOST"
echo -e "${BLUE}Reload:${NC} enabled"
echo ""

cd backend
exec uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
