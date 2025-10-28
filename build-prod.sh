#!/bin/bash
# Build Kahani for Production Deployment

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

echo -e "${GREEN}🔨 Building Kahani for Production${NC}"
echo ""

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

# Run database migrations
echo -e "${BLUE}🗄️ Running database migrations...${NC}"
cd backend && alembic upgrade head && cd ..
echo -e "${GREEN}✅ Database migrations complete${NC}"

# Download AI models if needed
echo -e "${BLUE}📦 Checking AI models...${NC}"
MODEL_CACHE="$HOME/.cache/huggingface/hub/"
EMBEDDING_MODEL_CACHE="$HOME/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2"
RERANKER_MODEL_CACHE="$HOME/.cache/huggingface/hub/models--cross-encoder--ms-marco-MiniLM-L-6-v2"

if [[ ! -d "$EMBEDDING_MODEL_CACHE" ]] || [[ ! -d "$RERANKER_MODEL_CACHE" ]]; then
    echo -e "${BLUE}📦 Downloading AI models...${NC}"
    cd backend
    python download_models.py || echo -e "${YELLOW}⚠️  Model download failed, will try at runtime${NC}"
    cd ..
    echo -e "${GREEN}✅ AI models downloaded${NC}"
else
    echo -e "${GREEN}✅ AI models already cached${NC}"
fi

# Build frontend for production
echo -e "${BLUE}🎨 Building frontend for production...${NC}"
cd frontend
npm run build
cd ..
echo -e "${GREEN}✅ Frontend built successfully${NC}"

# Verify build
if [[ ! -d "frontend/.next" ]]; then
    echo -e "${RED}❌ Frontend build failed - .next directory not found${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Production build complete!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}📁 Frontend build:${NC} frontend/.next/"
echo -e "${BLUE}🗄️ Database:${NC} backend/data/kahani.db"
echo -e "${BLUE}🤖 AI Models:${NC} $HOME/.cache/huggingface/hub/"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${GREEN}Ready to start production server with:${NC}"
echo -e "  ${BLUE}./start-prod.sh${NC}"
echo ""
