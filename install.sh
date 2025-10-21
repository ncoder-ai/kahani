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
    
    # Check available disk space (need at least 5GB for models)
    if [[ "$OS" == "linux" ]]; then
        available_space=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
    else
        available_space=$(df -g . | awk 'NR==2 {print $4}')
    fi
    
    if [[ $available_space -lt 5 ]]; then
        log_warning "Low disk space: ${available_space}GB available. Recommended: 5GB+ (includes AI models)"
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

# Download AI models
download_ai_models() {
    log_info "Downloading AI models for semantic memory..."
    log_info "This may take several minutes depending on your internet connection..."
    
    # Activate Python environment
    source .venv/bin/activate
    
    cd backend
    python download_models.py || {
        log_warning "Model download failed, but installation will continue"
        log_info "You can download models later by running: cd backend && python download_models.py"
    }
    cd ..
    
    log_success "AI models download complete"
}

# Setup database
setup_database() {
    log_info "Setting up database..."
    
    # Activate Python environment
    source .venv/bin/activate
    
    # Create required directories
    mkdir -p backend/data backend/backups backend/logs exports data/audio backend/data/chromadb
    
    # Check if database already exists
    if [[ -f backend/data/kahani.db ]]; then
        log_warning "Database already exists, skipping initialization"
        log_info "To recreate database, delete backend/data/kahani.db and run: cd backend && python init_database.py"
        return
    fi
    
    # Initialize database with all tables
    log_info "Initializing database schema and creating default users..."
    cd backend && python init_database.py && cd .. || {
        log_error "Database initialization failed"
        exit 1
    }
    
    log_success "Database setup complete"
}

# Create environment files
create_env_files() {
    log_info "Creating environment configuration files..."
    
    # Check if .env already exists in root
    if [[ -f .env ]]; then
        log_info ".env file already exists, skipping..."
        return
    fi
    
    # Check if .env.example exists
    if [[ ! -f .env.example ]]; then
        log_error ".env.example not found! Cannot create .env file."
        log_info "This file should be in the repository."
        exit 1
    fi
    
    # Copy .env.example to .env
    log_info "Creating .env file from .env.example..."
    cp .env.example .env
    
    # Generate secure secrets and replace placeholders
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    
    # Update secrets in .env file
    if [[ "$OS" == "macos" ]]; then
        sed -i '' "s|SECRET_KEY=.*|SECRET_KEY=\"$SECRET_KEY\"|g" .env
        sed -i '' "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=\"$JWT_SECRET_KEY\"|g" .env
    else
        sed -i "s|SECRET_KEY=.*|SECRET_KEY=\"$SECRET_KEY\"|g" .env
        sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=\"$JWT_SECRET_KEY\"|g" .env
    fi
    
    log_success "Created .env file with auto-generated secrets"
    log_warning "⚠️  Default admin credentials: admin@kahani.local / admin123"
    log_warning "⚠️  Please change these credentials after first login!"
    log_success "Environment files created"
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
    if [[ ! -f ".env" ]]; then
        log_error "Root .env configuration missing"
        ((errors++))
    else
        log_success "Configuration: OK"
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
    
    # Check AI models
    MODEL_CACHE="$HOME/.cache/huggingface/hub/"
    EMBEDDING_MODEL_CACHE="$MODEL_CACHE/models--sentence-transformers--all-MiniLM-L6-v2"
    RERANKER_MODEL_CACHE="$MODEL_CACHE/models--cross-encoder--ms-marco-MiniLM-L-6-v2"
    
    if [[ ! -d "$EMBEDDING_MODEL_CACHE" ]] || [[ ! -d "$RERANKER_MODEL_CACHE" ]]; then
        log_warning "AI models may not be fully downloaded"
        log_info "Run: cd backend && python download_models.py"
    else
        log_success "AI models: OK"
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
    
    # Download AI models
    download_ai_models
    
    # Setup database
    setup_database
    
    # Create configuration files
    create_env_files
    
    # Verify installation
    verify_installation
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🎉 Installation completed successfully!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "📋 Configuration Files Created:"
    echo "   ✓ .env                  (Application configuration)"
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
    echo "🌐 Access URLs (Development):"
    echo "   Application:       http://localhost:6789"
    echo "   API:              http://localhost:9876"
    echo "   API Documentation: http://localhost:9876/docs"
    echo ""
    echo "🌐 Network Access:"
    echo "   • Application auto-detects network IP"
    echo "   • Access from other devices: http://<your-ip>:6789"
    echo "   • CORS is configured for network access"
    echo ""
    echo "🤖 LLM Configuration:"
    echo "   • Default: LM Studio at http://localhost:1234"
    echo "   • Update in Settings page after login"
    echo "   • Or edit .env file: LLM_BASE_URL"
    echo ""
    echo "🧠 AI Models:"
    echo "   • Semantic memory models downloaded"
    echo "   • Located in: ~/.cache/huggingface/hub/"
    echo "   • Re-download: cd backend && python download_models.py"
    echo ""
    echo "📚 Documentation:"
    echo "   • README.md              - Project overview"
    echo "   • QUICK_START.md         - Quick start guide"
    echo "   • CONFIGURATION_GUIDE.md - Configuration details"
    echo "   • docs/                  - Feature documentation"
    echo ""
    echo "💡 Troubleshooting:"
    echo "   • Check logs: backend/logs/kahani.log"
    echo "   • Verify database: backend/data/kahani.db"
    echo "   • Test API: curl http://localhost:9876/health"
    echo "   • Network issues: Check .env CORS_ORIGINS"
    echo ""
    echo "🎯 Next Steps:"
    echo "   1. Start the application: ./start-dev.sh"
    echo "   2. Open http://localhost:6789 in your browser"
    echo "   3. Login with test@test.com / test"
    echo "   4. Configure LLM settings in Settings page"
    echo "   5. Start creating stories!"
    echo ""
    echo "❓ Need Help?"
    echo "   • GitHub: https://github.com/ncoder-ai/kahani"
    echo "   • Issues: https://github.com/ncoder-ai/kahani/issues"
    echo ""
}

# Run main function
main "$@"
