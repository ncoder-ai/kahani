#!/bin/bash
# Start Kahani Production Environment on Baremetal

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

echo -e "${GREEN}🚀 Starting Kahani Production Environment${NC}"
echo ""

# Function to handle cleanup
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down Kahani...${NC}"
    # Kill all child processes
    pkill -P $$ 2>/dev/null || true
    # Kill any remaining processes
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

# Check if frontend is built
if [[ ! -d "frontend/.next" ]]; then
    echo -e "${YELLOW}⚠️  Frontend not built for production!${NC}"
    echo "Building frontend for production..."
    cd frontend
    npm run build
    cd ..
    echo -e "${GREEN}✅ Frontend built successfully${NC}"
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

# Auto-detect network IP if NEXT_PUBLIC_API_URL is not set
if [[ -z "$NEXT_PUBLIC_API_URL" ]]; then
    # Try to detect network IP
    NETWORK_IP=$(python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2>/dev/null || echo "localhost")
    export NEXT_PUBLIC_API_URL="http://${NETWORK_IP}:${BACKEND_PORT}"
    echo -e "${BLUE}🌐 Auto-detected API URL: ${NEXT_PUBLIC_API_URL}${NC}"
fi

# Run Alembic migrations to upgrade schema before starting backend
echo -e "${BLUE}🗄️ Running Alembic migrations to upgrade database schema...${NC}"
cd backend && alembic upgrade head && cd ..

# Start backend with production settings
echo -e "${BLUE}📡 Starting backend server on port ${BACKEND_PORT}...${NC}"
cd backend
# Production settings: no reload, workers for better performance
PORT="$BACKEND_PORT" uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --workers 4 2>&1 | sed 's/^/[BACKEND] /' &
BACKEND_PID=$!
cd ..

# Wait for backend to start
echo -e "${BLUE}⏳ Waiting for backend to start...${NC}"
sleep 5

# Check if backend is running
if ! curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Backend might not be responding yet, giving it more time...${NC}"
    sleep 5
fi

# Verify backend is running
if curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend is running and healthy${NC}"
else
    echo -e "${RED}❌ Backend failed to start or is not responding${NC}"
    echo "Check the logs above for errors"
    exit 1
fi

# Start frontend with production build
echo -e "${BLUE}🎨 Starting frontend server on port ${FRONTEND_PORT}...${NC}"
cd frontend
# Production: serve the built Next.js app
PORT="$FRONTEND_PORT" npx next start 2>&1 | sed 's/^/[FRONTEND] /' &
FRONTEND_PID=$!
cd ..

# Wait for frontend to start
echo -e "${BLUE}⏳ Waiting for frontend to start...${NC}"
sleep 3

# Verify frontend is running
if curl -s http://localhost:$FRONTEND_PORT > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Frontend is running${NC}"
else
    echo -e "${YELLOW}⚠️  Frontend might not be responding yet${NC}"
fi

echo ""
echo -e "${GREEN}✅ Kahani Production Environment is running!${NC}"
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
echo -e "${GREEN}Production mode: Optimized for performance and stability${NC}"
echo -e "${GREEN}Press Ctrl+C to stop all servers${NC}"

# Log process IDs for monitoring
echo ""
echo -e "${BLUE}Process IDs:${NC}"
echo -e "  Backend PID: $BACKEND_PID"
echo -e "  Frontend PID: $FRONTEND_PID"
echo ""

# Wait for both processes
wait