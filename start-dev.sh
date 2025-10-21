#!/bin/bash
# Start Both Kahani Backend and Frontend Servers

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${GREEN}🚀 Starting Kahani Development Environment${NC}"
echo ""

# Function to handle cleanup
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down Kahani...${NC}"
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Check if virtual environment exists
if [[ ! -d ".venv" ]]; then
    echo -e "${RED}❌ Error: Virtual environment not found!${NC}"
    echo "Please run ./install.sh first"
    exit 1
fi

# Check if node_modules exists
if [[ ! -d "frontend/node_modules" ]]; then
    echo -e "${RED}❌ Error: Frontend dependencies not installed!${NC}"
    echo "Please run: cd frontend && npm install"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check and download AI models if needed
MODEL_CACHE="$HOME/.cache/huggingface/hub/"
EMBEDDING_MODEL_CACHE="$HOME/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2"
RERANKER_MODEL_CACHE="$HOME/.cache/huggingface/hub/models--cross-encoder--ms-marco-MiniLM-L-6-v2"

if [[ ! -d "$EMBEDDING_MODEL_CACHE" ]] || [[ ! -d "$RERANKER_MODEL_CACHE" ]]; then
    echo -e "${BLUE}📦 Downloading AI models (one-time setup)...${NC}"
    cd backend
    python download_models.py || echo -e "${YELLOW}⚠️  Model download failed, will try at runtime${NC}"
    cd ..
else
    echo -e "${GREEN}✅ AI models already cached${NC}"
fi

# Setup environment if .env doesn't exist
if [[ ! -f .env ]]; then
    echo -e "${YELLOW}⚠️  .env file not found, setting up environment...${NC}"
    ./setup-env.sh
fi

# Load environment variables from .env file at project root
if [[ -f .env ]]; then
    echo -e "${BLUE}📄 Loading environment variables from .env${NC}"
    set -a
    source .env
    set +a
fi

# Load configuration from config.yaml
if [[ -f config.yaml ]]; then
    export BACKEND_PORT=$(grep -A 2 'backend:' config.yaml | grep 'port:' | grep -o '[0-9]*')
    export FRONTEND_PORT=$(grep -A 2 'frontend:' config.yaml | grep 'port:' | grep -o '[0-9]*')
    # API URL will be auto-detected by the network configuration utility
fi

# Set defaults
export PYTHONPATH="${SCRIPT_DIR}/backend"
BACKEND_PORT="${BACKEND_PORT:-9876}"
FRONTEND_PORT="${FRONTEND_PORT:-6789}"

# Start backend
echo -e "${BLUE}📡 Starting backend server on port ${BACKEND_PORT}...${NC}"
cd backend
PORT="$BACKEND_PORT" uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT" 2>&1 | sed 's/^/[BACKEND] /' &
BACKEND_PID=$!
cd ..

# Wait for backend to start
echo -e "${BLUE}⏳ Waiting for backend to start...${NC}"
sleep 3

# Check if backend is running
if ! curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Backend might not be responding yet, giving it more time...${NC}"
    sleep 3
fi

# Load frontend env if exists
if [[ -f frontend/.env.local ]]; then
    set -a
    source frontend/.env.local
    set +a
fi

# Start frontend
echo -e "${BLUE}🎨 Starting frontend server on port ${FRONTEND_PORT}...${NC}"
cd frontend
PORT="$FRONTEND_PORT" npm run dev 2>&1 | sed 's/^/[FRONTEND] /' &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${GREEN}✅ Kahani is running!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}📖 Frontend:${NC}     http://localhost:$FRONTEND_PORT"
echo -e "${BLUE}📡 Backend API:${NC}  http://localhost:$BACKEND_PORT"
echo -e "${BLUE}📚 API Docs:${NC}     http://localhost:$BACKEND_PORT/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${BLUE}💡 Default login:${NC} test@test.com / test"
echo -e "${BLUE}🔧 Admin login:${NC}   admin@kahani.local / admin123"
echo ""
echo -e "${YELLOW}⚠️  Make sure your LLM service is running${NC}"
echo -e "${YELLOW}   (default: http://localhost:1234)${NC}"
echo ""
echo -e "${GREEN}Press Ctrl+C to stop all servers${NC}"

# Wait for both processes
wait
