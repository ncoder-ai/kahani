#!/bin/bash

# Kahani Installation Script
# Supports Linux and macOS
# Author: Kahani Team
# Description: Automated installation script for Kahani storytelling platform

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    else
        log_error "Unsupported operating system: $OSTYPE"
        exit 1
    fi
    log_info "Detected OS: $OS"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install system dependencies
install_system_deps() {
    log_info "Installing system dependencies..."
    
    if [[ "$OS" == "linux" ]]; then
        # Update package list
        sudo apt update
        
        # Install required packages
        sudo apt install -y curl wget git build-essential libssl-dev zlib1g-dev \
            libbz2-dev libreadline-dev libsqlite3-dev llvm libncurses5-dev \
            libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev
            
    elif [[ "$OS" == "macos" ]]; then
        # Check if Homebrew is installed
        if ! command_exists brew; then
            log_info "Installing Homebrew..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        
        # Install required packages
        brew install curl wget git openssl readline sqlite3 xz zlib
    fi
    
    log_success "System dependencies installed"
}

# Install Python
install_python() {
    if command_exists python3.11; then
        log_info "Python 3.11 already installed"
        return
    fi
    
    log_info "Installing Python 3.11..."
    
    if [[ "$OS" == "linux" ]]; then
        # Install Python 3.11 via deadsnakes PPA
        sudo apt update
        sudo apt install -y software-properties-common
        sudo add-apt-repository -y ppa:deadsnakes/ppa
        sudo apt update
        sudo apt install -y python3.11 python3.11-venv python3.11-pip
        
    elif [[ "$OS" == "macos" ]]; then
        brew install python@3.11
    fi
    
    log_success "Python 3.11 installed"
}

# Install Node.js
install_nodejs() {
    if command_exists node && [[ $(node -v | cut -d'v' -f2 | cut -d'.' -f1) -ge 18 ]]; then
        log_info "Node.js 18+ already installed"
        return
    fi
    
    log_info "Installing Node.js..."
    
    # Install Node.js via NodeSource
    if [[ "$OS" == "linux" ]]; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
        
    elif [[ "$OS" == "macos" ]]; then
        brew install node
    fi
    
    log_success "Node.js installed"
}

# Setup Python virtual environment
setup_python_env() {
    log_info "Setting up Python virtual environment..."
    
    # Create virtual environment
    python3.11 -m venv .venv
    
    # Activate virtual environment
    source .venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install Python dependencies
    log_info "Installing Python dependencies..."
    pip install -r backend/requirements.txt
    
    log_success "Python environment setup complete"
}

# Setup Node.js dependencies
setup_nodejs_env() {
    log_info "Setting up Node.js environment..."
    
    cd frontend
    
    # Install dependencies
    npm install
    
    cd ..
    
    log_success "Node.js environment setup complete"
}

# Setup database
setup_database() {
    log_info "Setting up database..."
    
    # Activate Python environment
    source .venv/bin/activate
    
    # Create data directory
    mkdir -p backend/data
    
    # Run database migrations
    cd backend
    python migrate_add_auto_open_last_story.py
    python migrate_add_prompt_templates.py
    cd ..
    
    log_success "Database setup complete"
}

# Create environment files
create_env_files() {
    log_info "Creating environment configuration files..."
    
    # Backend .env
    if [[ ! -f backend/.env ]]; then
        cat > backend/.env << EOF
# Kahani Backend Configuration
APP_NAME="Kahani"
APP_VERSION="1.0.0"
DEBUG=true
LOG_LEVEL="INFO"
LOG_FILE="logs/app.log"

# Security
SECRET_KEY="your-secret-key-here-please-change-in-production"
ACCESS_TOKEN_EXPIRE_MINUTES=720

# Database
DATABASE_URL="sqlite:///./data/kahani.db"

# CORS
CORS_ORIGINS=["http://localhost:3000", "http://localhost:3001", "http://localhost:8080"]

# LLM Configuration (LM Studio defaults)
LLM_BASE_URL="http://localhost:1234/v1"
LLM_API_KEY="not-needed-for-local"
LLM_MODEL="local-model"
LLM_MAX_TOKENS=2048
LLM_TEMPERATURE=0.7
EOF
        log_info "Created backend/.env file"
    fi
    
    # Frontend .env.local
    if [[ ! -f frontend/.env.local ]]; then
        cat > frontend/.env.local << EOF
# Kahani Frontend Configuration
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
EOF
        log_info "Created frontend/.env.local file"
    fi
    
    log_success "Environment files created"
}

# Create startup scripts
create_startup_scripts() {
    log_info "Creating startup scripts..."
    
    # Development startup script
    cat > start-dev.sh << 'EOF'
#!/bin/bash
# Kahani Development Startup Script

echo "🚀 Starting Kahani in development mode..."

# Function to handle cleanup
cleanup() {
    echo "🛑 Shutting down Kahani..."
    kill $(jobs -p) 2>/dev/null
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start backend
echo "📡 Starting backend server..."
cd backend
source ../.venv/bin/activate
PYTHONPATH=$(pwd) python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to start
sleep 3

# Start frontend
echo "🎨 Starting frontend server..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo "✅ Kahani is starting up!"
echo "📖 Frontend: http://localhost:3000"
echo "📡 Backend API: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all servers"

# Wait for both processes
wait
EOF
    
    chmod +x start-dev.sh
    
    # Production startup script
    cat > start-prod.sh << 'EOF'
#!/bin/bash
# Kahani Production Startup Script

echo "🚀 Starting Kahani in production mode..."

# Function to handle cleanup
cleanup() {
    echo "🛑 Shutting down Kahani..."
    kill $(jobs -p) 2>/dev/null
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Build frontend
echo "🔨 Building frontend..."
cd frontend
npm run build
cd ..

# Start backend
echo "📡 Starting backend server..."
cd backend
source ../.venv/bin/activate
PYTHONPATH=$(pwd) python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Start frontend
echo "🎨 Starting frontend server..."
cd frontend
npm start &
FRONTEND_PID=$!
cd ..

echo "✅ Kahani is running in production mode!"
echo "🌐 Application: http://localhost:3000"
echo "📡 Backend API: http://localhost:8000"

# Wait for both processes
wait
EOF
    
    chmod +x start-prod.sh
    
    log_success "Startup scripts created"
}

# Main installation function
main() {
    echo "🎭 Kahani Installation Script"
    echo "=============================="
    echo ""
    
    # Check if we're in the right directory
    if [[ ! -f "backend/app/main.py" ]] || [[ ! -f "frontend/package.json" ]]; then
        log_error "Please run this script from the root directory of the Kahani project"
        exit 1
    fi
    
    detect_os
    
    log_info "Starting Kahani installation..."
    
    # Install dependencies
    install_system_deps
    install_python
    install_nodejs
    
    # Setup environments
    setup_python_env
    setup_nodejs_env
    
    # Setup database
    setup_database
    
    # Create configuration files
    create_env_files
    
    # Create startup scripts
    create_startup_scripts
    
    echo ""
    echo "🎉 Installation completed successfully!"
    echo ""
    echo "📋 Next steps:"
    echo "1. Review and update configuration files:"
    echo "   - backend/.env (especially SECRET_KEY and LLM settings)"
    echo "   - frontend/.env.local"
    echo ""
    echo "2. Start the application:"
    echo "   - Development mode: ./start-dev.sh"
    echo "   - Production mode: ./start-prod.sh"
    echo ""
    echo "3. Open your browser and visit:"
    echo "   - Application: http://localhost:3000"
    echo "   - API Documentation: http://localhost:8000/docs"
    echo ""
    echo "📚 For more information, see README.md"
    echo ""
    echo "🤖 Make sure to have LM Studio running on http://localhost:1234"
    echo "    or update the LLM configuration in backend/.env"
    echo ""
}

# Run main function
main "$@"