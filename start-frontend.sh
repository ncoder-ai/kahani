#!/bin/bash
# Start Kahani Frontend Server

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if node_modules exists
if [[ ! -d "frontend/node_modules" ]]; then
    echo -e "${RED}Error: Frontend dependencies not installed!${NC}"
    echo "Please run: cd frontend && npm install"
    exit 1
fi

# Load environment variables from root .env
if [[ -f .env ]]; then
    echo -e "${BLUE}Loading .env...${NC}"
    set -a
    source .env
    set +a
fi

# Load configuration from config.yaml
if [[ -f config.yaml ]]; then
    export FRONTEND_PORT=$(grep -A 2 'frontend:' config.yaml | grep 'port:' | grep -o '[0-9]*')
    export NEXT_PUBLIC_API_URL=$(grep -A 2 'frontend:' config.yaml | grep 'apiUrl:' | awk '{print $2}')
fi

# Set defaults if not provided
export PORT="${FRONTEND_PORT:-6789}"

echo -e "${GREEN}Starting Kahani Frontend Server...${NC}"
echo -e "${BLUE}Port:${NC} $PORT"
echo ""

cd frontend
exec npm run dev
