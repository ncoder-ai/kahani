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

# Check system requirements
check_requirements() {
    log_info "Checking system requirements..."
    
    local missing_deps=()
    
    # Check for essential tools
    if ! command_exists curl; then
        missing_deps+=("curl")
    fi
    
    if ! command_exists git; then
        missing_deps+=("git")
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_deps[*]}"
        log_info "Please install these tools before continuing"
        exit 1
    fi
    
    # Check available disk space (need at least 2GB)
    if [[ "$OS" == "linux" ]]; then
        available_space=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
    else
        available_space=$(df -g . | awk 'NR==2 {print $4}')
    fi
    
    if [[ $available_space -lt 2 ]]; then
        log_warning "Low disk space: ${available_space}GB available. Recommended: 2GB+"
    fi
    
    log_success "System requirements check passed"
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
    mkdir -p backend/backups
    mkdir -p backend/logs
    mkdir -p data
    mkdir -p logs
    mkdir -p exports
    
    # Check if database already exists
    if [[ -f backend/data/kahani.db ]]; then
        log_warning "Database already exists at backend/data/kahani.db"
        read -p "Do you want to recreate the database? This will DELETE all existing data! (yes/no): " -r
        echo
        if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            log_warning "Backing up existing database..."
            BACKUP_NAME="kahani_backup_$(date +%Y%m%d_%H%M%S).db"
            cp backend/data/kahani.db "backend/backups/$BACKUP_NAME"
            log_info "Backup saved to backend/backups/$BACKUP_NAME"
            rm backend/data/kahani.db
        else
            log_info "Keeping existing database"
            return
        fi
    fi
    
    # Initialize database with all tables
    log_info "Initializing database schema and creating default users..."
    cd backend
    python init_database.py
    cd ..
    
    log_success "Database setup complete"
}

# Create environment files
create_env_files() {
    log_info "Creating environment configuration files..."
    
    # Backend .env
    if [[ ! -f backend/.env ]]; then
        # Generate a random secret key
        SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
        JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
        
        cat > backend/.env << EOF
# Kahani Backend Configuration
APP_NAME="Kahani"
APP_VERSION="1.0.0"
DEBUG=true
LOG_LEVEL="INFO"
LOG_FILE="logs/kahani.log"

# Security
SECRET_KEY="$SECRET_KEY"
JWT_SECRET_KEY="$JWT_SECRET_KEY"
ACCESS_TOKEN_EXPIRE_MINUTES=720

# Default Admin Account
ADMIN_EMAIL="admin@kahani.local"
ADMIN_PASSWORD="admin123"

# Database
DATABASE_URL="sqlite:///./data/kahani.db"

# CORS
CORS_ORIGINS=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://0.0.0.0:3000"]

# LLM Configuration (LM Studio defaults)
LLM_BASE_URL="http://localhost:1234/v1"
LLM_API_KEY="not-needed-for-local"
LLM_MODEL="local-model"
LLM_MAX_TOKENS=2048
LLM_TEMPERATURE=0.7

# Context Management
MAX_CONTEXT_TOKENS=8000
CONTEXT_WARNING_THRESHOLD=6400

# Scene Generation
DEFAULT_SCENE_LENGTH="medium"
SCENE_GENERATION_TIMEOUT=60

# TTS Configuration (Optional)
TTS_ENABLED=false
TTS_PROVIDER="chatterbox"
TTS_API_URL="http://localhost:8010"

# Storage
UPLOAD_DIR="./uploads"
EXPORT_DIR="./exports"
BACKUP_DIR="./backups"
EOF
        log_success "Created backend/.env file with auto-generated secrets"
        log_warning "⚠️  Default admin credentials: admin@kahani.local / admin123"
        log_warning "⚠️  Please change these credentials after first login!"
    else
        log_info "backend/.env already exists, skipping..."
    fi
    
    # Frontend .env.local
    if [[ ! -f frontend/.env.local ]]; then
        cat > frontend/.env.local << EOF
# Kahani Frontend Configuration
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

# Optional: Analytics and monitoring
# NEXT_PUBLIC_GA_ID=your-google-analytics-id
EOF
        log_success "Created frontend/.env.local file"
    else
        log_info "frontend/.env.local already exists, skipping..."
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

set -e

echo "🚀 Starting Kahani in development mode..."

# Check if virtual environment exists
if [[ ! -d ".venv" ]]; then
    echo "❌ Error: Virtual environment not found!"
    echo "Please run ./install.sh first"
    exit 1
fi

# Check if backend/.env exists
if [[ ! -f "backend/.env" ]]; then
    echo "❌ Error: Backend configuration not found!"
    echo "Please run ./install.sh first"
    exit 1
fi

# Check if database exists
if [[ ! -f "backend/data/kahani.db" ]]; then
    echo "❌ Error: Database not initialized!"
    echo "Please run ./install.sh first"
    exit 1
fi

# Function to handle cleanup
cleanup() {
    echo ""
    echo "🛑 Shutting down Kahani..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start backend
echo "📡 Starting backend server..."
cd backend
source ../.venv/bin/activate
export PYTHONPATH=$(pwd)
export $(grep -v '^#' .env | xargs)
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 2>&1 | sed 's/^/[BACKEND] /' &
BACKEND_PID=$!
cd ..

# Wait for backend to start
echo "⏳ Waiting for backend to start..."
sleep 5

# Check if backend is running
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "⚠️  Warning: Backend might not be responding yet, giving it more time..."
    sleep 3
fi

# Start frontend
echo "🎨 Starting frontend server..."
cd frontend
npm run dev 2>&1 | sed 's/^/[FRONTEND] /' &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Kahani is running!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📖 Frontend:     http://localhost:3000"
echo "📡 Backend API:  http://localhost:8000"
echo "📚 API Docs:     http://localhost:8000/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "💡 Default login: test@test.com / test"
echo "🔧 Admin login:   admin@kahani.local / admin123"
echo ""
echo "⚠️  Make sure LM Studio is running at http://localhost:1234"
echo "   or update LLM_BASE_URL in backend/.env"
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

set -e

echo "🚀 Starting Kahani in production mode..."

# Check if virtual environment exists
if [[ ! -d ".venv" ]]; then
    echo "❌ Error: Virtual environment not found!"
    echo "Please run ./install.sh first"
    exit 1
fi

# Function to handle cleanup
cleanup() {
    echo ""
    echo "🛑 Shutting down Kahani..."
    kill $(jobs -p) 2>/dev/null || true
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
export PYTHONPATH=$(pwd)
export $(grep -v '^#' .env | xargs)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 2>&1 | sed 's/^/[BACKEND] /' &
BACKEND_PID=$!
cd ..

# Start frontend
echo "🎨 Starting frontend server..."
cd frontend
npm start 2>&1 | sed 's/^/[FRONTEND] /' &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Kahani is running in production mode!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 Application:  http://localhost:3000"
echo "📡 Backend API:  http://localhost:8000"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Press Ctrl+C to stop all servers"

# Wait for both processes
wait
EOF
    
    chmod +x start-prod.sh
    
    log_success "Startup scripts created"
}

# Verify installation
verify_installation() {
    log_info "Verifying installation..."
    
    local errors=0
    
    # Check Python environment
    if [[ ! -d ".venv" ]]; then
        log_error "Virtual environment not found"
        ((errors++))
    else
        log_success "Virtual environment: OK"
    fi
    
    # Check database
    if [[ ! -f "backend/data/kahani.db" ]]; then
        log_error "Database not found"
        ((errors++))
    else
        log_success "Database: OK"
    fi
    
    # Check configuration files
    if [[ ! -f "backend/.env" ]]; then
        log_error "Backend configuration missing"
        ((errors++))
    else
        log_success "Backend config: OK"
    fi
    
    if [[ ! -f "frontend/.env.local" ]]; then
        log_error "Frontend configuration missing"
        ((errors++))
    else
        log_success "Frontend config: OK"
    fi
    
    # Check startup scripts
    if [[ ! -x "start-dev.sh" ]]; then
        log_error "Development startup script missing or not executable"
        ((errors++))
    else
        log_success "Startup scripts: OK"
    fi
    
    # Check Node modules
    if [[ ! -d "frontend/node_modules" ]]; then
        log_warning "Frontend dependencies might be incomplete"
    else
        log_success "Frontend dependencies: OK"
    fi
    
    # Check Python packages
    source .venv/bin/activate
    if ! python -c "import fastapi" 2>/dev/null; then
        log_error "Python dependencies incomplete"
        ((errors++))
    else
        log_success "Backend dependencies: OK"
    fi
    deactivate
    
    if [[ $errors -gt 0 ]]; then
        log_error "Installation verification failed with $errors error(s)"
        log_warning "Please review the errors above and re-run the installation"
        exit 1
    fi
    
    log_success "Installation verification passed!"
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
    check_requirements
    
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
    
    # Verify installation
    verify_installation
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎉 Installation completed successfully!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "📋 Configuration Files Created:"
    echo "   ✓ backend/.env          (Backend configuration)"
    echo "   ✓ frontend/.env.local   (Frontend configuration)"
    echo ""
    echo "🔐 Default Accounts Created:"
    echo "   • User:  test@test.com / test"
    echo "   • Admin: admin@kahani.local / admin123"
    echo "   ⚠️  Change these credentials after first login!"
    echo ""
    echo "🚀 Start the Application:"
    echo "   Development:  ./start-dev.sh"
    echo "   Production:   ./start-prod.sh"
    echo ""
    echo "🌐 Access URLs:"
    echo "   Application:       http://localhost:3000"
    echo "   API:              http://localhost:8000"
    echo "   API Documentation: http://localhost:8000/docs"
    echo ""
    echo "🤖 LLM Configuration:"
    echo "   • Make sure LM Studio is running at http://localhost:1234"
    echo "   • Or update LLM_BASE_URL in backend/.env"
    echo ""
    echo "📚 Documentation:"
    echo "   • README.md              - Project overview"
    echo "   • docs/                  - Detailed documentation"
    echo "   • backend/.env           - Backend configuration"
    echo ""
    echo "💡 Troubleshooting:"
    echo "   • Check logs: backend/logs/kahani.log"
    echo "   • Verify database: backend/data/kahani.db"
    echo "   • Test API: curl http://localhost:8000/health"
    echo ""
    echo "❓ Need Help?"
    echo "   • GitHub Issues: https://github.com/ncoder-ai/kahani/issues"
    echo "   • Documentation: See docs/ directory"
    echo ""
}

# Run main function
main "$@"