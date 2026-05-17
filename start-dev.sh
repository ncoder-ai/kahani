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
EMBEDDING_MODEL_CACHE="$HOME/.cache/huggingface/hub/models--sentence-transformers--all-mpnet-base-v2"
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

# Auto-copy example config files if missing
if [[ ! -f config.yaml ]] && [[ -f config.yaml.example ]]; then
    cp config.yaml.example config.yaml
    echo -e "${BLUE}📄 Created config.yaml from config.yaml.example${NC}"
fi

# Load configuration from config.yaml
if [[ -f config.yaml ]]; then
    echo -e "${BLUE}📄 Reading configuration from config.yaml${NC}"
    export BACKEND_PORT=$(python3 read-config.py backend_port) || {
        echo -e "${RED}❌ Failed to read backend port from config.yaml${NC}"
        exit 1
    }
    export FRONTEND_PORT=$(python3 read-config.py frontend_port) || {
        echo -e "${RED}❌ Failed to read frontend port from config.yaml${NC}"
        exit 1
    }
    echo -e "${BLUE}   Backend port: ${BACKEND_PORT}${NC}"
    echo -e "${BLUE}   Frontend port: ${FRONTEND_PORT}${NC}"
else
    echo -e "${RED}❌ config.yaml not found${NC}"
    echo -e "${RED}   Please ensure config.yaml exists in the project root${NC}"
    exit 1
fi

# Set Python path
export PYTHONPATH="${SCRIPT_DIR}/backend"

# Try to detect network IP for display purposes
NETWORK_IP=$(python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo "localhost")

# Set NEXT_PUBLIC_API_URL for local development if not already set in .env
# For local development: use localhost with backend port
# For production/reverse proxy: set NEXT_PUBLIC_API_URL in .env or environment
if [[ -z "$NEXT_PUBLIC_API_URL" ]]; then
    # Local development: set to localhost with backend port
    export NEXT_PUBLIC_API_URL="http://localhost:${BACKEND_PORT}"
    echo -e "${BLUE}🌐 Setting NEXT_PUBLIC_API_URL for local development: ${NEXT_PUBLIC_API_URL}${NC}"
    echo -e "${BLUE}💡 Tip: Add NEXT_PUBLIC_API_URL to .env if you want to persist this setting${NC}"
else
    echo -e "${BLUE}🌐 Using NEXT_PUBLIC_API_URL from .env: ${NEXT_PUBLIC_API_URL}${NC}"
fi

# Next.js will pick up NEXT_PUBLIC_API_URL from the environment (exported above)
# .env file is kept clean with only secrets - optional overrides can be added manually


# Run Alembic migrations to upgrade schema before starting backend
echo -e "${BLUE}🗄️ Running Alembic migrations to upgrade database schema...${NC}"
cd backend && alembic upgrade head && cd ..

# Start backend (venv is already activated at line 46)
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

# Start frontend
# NEXT_PUBLIC_API_URL is already exported from base .env (or set above)
# Next.js will pick it up from the environment
echo -e "${BLUE}🎨 Starting frontend server on port ${FRONTEND_PORT}...${NC}"
cd frontend
# Explicitly pass NEXT_PUBLIC_API_URL to ensure Next.js picks it up
PORT="$FRONTEND_PORT" NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" npm run dev 2>&1 | sed 's/^/[FRONTEND] /' &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${GREEN}✅ Kahani is running!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}📖 Frontend (local):${NC}    http://localhost:$FRONTEND_PORT"
if [[ "$NETWORK_IP" != "localhost" ]]; then
    echo -e "${BLUE}📖 Frontend (network):${NC}  http://$NETWORK_IP:$FRONTEND_PORT"
fi
echo -e "${BLUE}📡 Backend API (local):${NC} http://localhost:$BACKEND_PORT"
if [[ "$NETWORK_IP" != "localhost" ]]; then
    echo -e "${BLUE}📡 Backend API (network):${NC} http://$NETWORK_IP:$BACKEND_PORT"
fi
echo -e "${BLUE}📚 API Docs:${NC}            http://localhost:$BACKEND_PORT/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${BLUE}🔐 First user to register becomes admin automatically${NC}"
echo -e "${BLUE}💡 No default users - register your first account to get started${NC}"
echo ""
echo -e "${YELLOW}⚠️  Make sure your LLM service is running${NC}"
echo -e "${YELLOW}   (default: http://localhost:1234)${NC}"
echo ""
echo -e "${GREEN}Press Ctrl+C to stop all servers${NC}"

# Wait for both processes
wait
